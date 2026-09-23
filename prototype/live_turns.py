"""Item-scoped audio accounting. No transcript or audio is persisted here."""
from collections import deque
import time

from .live_audio import is_silent_pcm16le


class TurnLedger:
    def __init__(self, vad_reason='server_vad'):
        self.vad_reason = vad_reason
        self.samples = 0
        self.allocated = 0
        self.frames = []
        self.items = {}
        self.intents = []
        self.ready = deque()
        self.delivered = set()

    def append(self, pcm):
        end = self.samples + len(pcm) // 2
        self.frames.append((self.samples, end, not is_silent_pcm16le(pcm)))
        self.samples = end

    def meaningful(self, start, end):
        return any(a < end and b > start and speech for a, b, speech in self.frames)

    @property
    def cursor(self):
        return max([self.allocated] + [x['end'] for x in self.intents])

    @property
    def pending_seconds(self):
        return (self.samples - self.cursor) / 24000

    @property
    def meaningful_pending_seconds(self):
        """Age from first meaningful uncommitted frame, not silent pre-roll.

        Keep intervening pauses in the bound; this is not summed voiced time.
        Ownership advances on commit, never on an older item's completion.
        This clock does not discard or change the committed audio range.
        """
        cursor = self.cursor
        for start, end, speech in self.frames:
            if speech and end > cursor:
                return (self.samples - max(start, cursor)) / 24000
        return 0.0

    def request(self, sequence, reason, event_id=None):
        self.intents.append(dict(sequence=sequence, reason=reason, start=self.cursor,
                                 end=self.samples, at=time.monotonic(), event_id=event_id))

    def reconcile_empty_commit(self, event_id):
        """A rejected redundant commit is not an empty transcription.

        Only retire the sole intent if VAD already owns its meaningful range.
        Its items remain pending until their own completion is handled.
        """
        if len(self.intents) != 1:
            return False
        intent = self.intents[0]
        if event_id is not None and event_id != intent['event_id']:
            return False
        covered = any(item.get('reason') in {'server_vad', 'semantic_vad'}
                      and item.get('start') is not None
                      and item['start'] <= intent['start'] < item['end']
                      and item['end'] >= min(intent['end'], self.allocated)
                      for item in self.items.values())
        if not covered or self.meaningful(self.allocated, intent['end']):
            return False
        self.intents.pop()
        return True

    def observe(self, raw):
        typ, key = raw.get('type'), raw.get('item_id')
        if not key:
            return
        item = self.items.setdefault(key, {})
        if typ == 'input_audio_buffer.speech_started':
            item['vad_start'] = raw.get('audio_start_ms')
        elif typ == 'input_audio_buffer.speech_stopped':
            item['vad_end'] = raw.get('audio_end_ms')
            item['vad_event_id'] = raw.get('event_id')
        elif typ == 'input_audio_buffer.committed' and 'start' not in item:
            item['previous'] = raw.get('previous_item_id')
            item['boundary_event_id'] = item.get('vad_event_id') or raw.get('event_id')
            item['at'] = time.monotonic()
            if 'vad_end' in item:
                end = round(item['vad_end'] * 24)
                item.update(start=self.allocated, end=end, reason=self.vad_reason, sequence=None)
            elif self.intents:
                intent = self.intents.pop(0)
                item.update(start=intent['start'], end=intent['end'],
                            reason=intent['reason'], sequence=intent['sequence'])
                if intent['start'] < self.allocated:
                    # A VAD acknowledgement consumed overlapping input before
                    # this explicit acknowledgement. Do not invent ownership.
                    item.update(start=None, end=None)
            else:
                item.update(start=None, end=None, reason='unknown', sequence=None)
            if item['end'] is not None:
                self.allocated = max(self.allocated, item['end'])

    def context(self, key):
        item = self.items.get(key, {})
        start, end = item.get('start'), item.get('end')
        known = start is not None and end is not None and 0 <= start <= end <= self.samples
        indices = [i for i, (a, b, _) in enumerate(self.frames)
                   if known and a < end and b > start]
        return dict(item_id=key, range_known=known,
                    audio_start=start / 24000 if known else None,
                    audio_end=end / 24000 if known else None,
                    frame_start=indices[0] if indices else None,
                    frame_end=indices[-1] if indices else None,
                    meaningful=self.meaningful(start, end) if known else None,
                    boundary_reason=item.get('reason', 'unknown'),
                    boundary_event_id=item.get('boundary_event_id'),
                    local_commit_sequence=item.get('sequence'))

    def complete(self, key, event):
        item = self.items.setdefault(key, {})
        if 'completion' in item:
            return dict(type='duplicate_final', item_id=key)
        item['completion'] = event
        # Hold younger completions until predecessors have been emitted. This
        # preserves Evidence/Analyzer FIFO without assuming completion ordering.
        self.release()
        return self.ready.popleft() if self.ready else dict(type='ignored')

    def release(self):
        changed = True
        while changed:
            changed = False
            for key, item in self.items.items():
                previous = item.get('previous')
                if ('completion' in item and not item.get('emitted')
                        and (previous is None or self.items.get(previous, {}).get('emitted'))):
                    item['emitted'] = True
                    self.ready.append(item['completion'])
                    changed = True

    def acknowledge(self, key):
        self.delivered.add(key)

    def pending(self):
        return bool(self.intents or any('start' in item and key not in self.delivered
                                       for key, item in self.items.items()))

    def expired(self, timeout):
        now = time.monotonic()
        return any(now - x['at'] > timeout for x in self.intents) or any(
            'at' in item and key not in self.delivered and now-item['at'] > timeout
            for key, item in self.items.items())
