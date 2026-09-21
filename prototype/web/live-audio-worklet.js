/* L1 microphone capture only.  No STT, Analyzer, Event, or Graph code lives here. */
class DiscussionMapCaptureProcessor extends AudioWorkletProcessor {
  process(inputs) {
    const input = inputs[0];
    if (!input || input.length === 0 || input[0].length === 0) return true;
    const frameCount = input[0].length;
    const mono = new Float32Array(frameCount);
    for (let frame = 0; frame < frameCount; frame += 1) {
      let sum = 0;
      for (let channel = 0; channel < input.length; channel += 1) {
        sum += input[channel][frame] || 0;
      }
      mono[frame] = sum / input.length;
    }
    this.port.postMessage({ type: 'pcm', sampleRate, samples: mono }, [mono.buffer]);
    return true;
  }
}

registerProcessor('discussion-map-capture', DiscussionMapCaptureProcessor);
