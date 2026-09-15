class HearthRecorder extends AudioWorkletProcessor {
  process(inputs) {
    const input = inputs[0]?.[0];
    // Forward each render quantum so Stop does not discard a partly filled buffer.
    if (input) this.port.postMessage(input);
    return true;
  }
}
registerProcessor('hearth-recorder', HearthRecorder);
