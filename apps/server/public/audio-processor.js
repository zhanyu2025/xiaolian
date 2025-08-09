// audio-processor.js

/**
 * An AudioWorkletProcessor that buffers raw PCM audio data.
 *
 * This processor's job is to solve the problem of browsers sending many small
 * audio packets (typically 128 samples). It accumulates these small packets
 * into a larger, fixed-size buffer. Once the buffer is full, it sends the
 * complete, well-formed PCM data block to the main thread. This ensures the
 * server receives audio data in predictable, manageable chunks, which is
 * crucial for clean recording and real-time processing.
 *
 * This processor does NOT perform any encoding (like Opus); it only deals with
 * raw 16-bit PCM data.
 */
class PcmBufferProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    // 60ms of audio at 16kHz = 960 samples. This is a common frame size
    // for voice activity detectors and other speech processing systems.
    this.frameSize = 960;
    this.buffer = new Int16Array(this.frameSize);
    this.bufferIndex = 0;
    this.isRecording = false;

    // Listens for 'start' and 'stop' commands from the main thread.
    this.port.onmessage = (event) => {
      if (event.data.command === "start") {
        this.isRecording = true;
      } else if (event.data.command === "stop") {
        this.isRecording = false;
        // When stopping, flush any remaining audio data that hasn't filled a full frame.
        this.flush();
      }
    };
  }

  /**
   * Sends any remaining data in the buffer to the main thread.
   */
  flush() {
    if (this.bufferIndex > 0) {
      // Send only the part of the buffer that contains actual data.
      const finalBuffer = this.buffer.slice(0, this.bufferIndex);
      // Post the underlying ArrayBuffer, transferring ownership for efficiency.
      this.port.postMessage(finalBuffer.buffer, [finalBuffer.buffer]);
    }
    this.bufferIndex = 0; // Reset for the next recording session.
  }

  /**
   * The core processing function, called by the browser's audio engine.
   * @param {Float32Array[][]} inputs - The incoming audio data.
   * @returns {boolean} - true to keep the processor alive.
   */
  process(inputs) {
    if (!this.isRecording) {
      return true;
    }

    // We only process the first input and its first channel (mono).
    const inputChannel = inputs[0][0];
    if (!inputChannel) {
      return true;
    }

    // Process each incoming sample from the small 128-sample block.
    for (let i = 0; i < inputChannel.length; i++) {
      // Convert the Float32 sample (range -1.0 to 1.0) to a 16-bit PCM integer.
      // Clamping is used to prevent clipping.
      const sample = Math.max(-1, Math.min(1, inputChannel[i]));
      this.buffer[this.bufferIndex++] =
        sample < 0 ? sample * 0x8000 : sample * 0x7fff;

      // If our large buffer is full, send it to the main thread.
      if (this.bufferIndex === this.frameSize) {
        this.port.postMessage(this.buffer.buffer, [this.buffer.buffer]);

        // Create a new buffer for the next chunk and reset the index.
        this.buffer = new Int16Array(this.frameSize);
        this.bufferIndex = 0;
      }
    }

    return true;
  }
}

// Register the processor so it can be instantiated by name in the main thread.
registerProcessor("pcm-buffer-processor", PcmBufferProcessor);
