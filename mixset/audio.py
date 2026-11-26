"""Shared helpers: decode, lag against a reference, frame levels."""
import subprocess
import numpy as np
from scipy.signal import fftconvolve

SR = 44100


def decode(path, sr=SR, ch=2):
    """Float samples, (n, ch), exactly as ffmpeg decodes them (no clipping of overs)."""
    r = subprocess.run(['ffmpeg', '-v', 'error', '-i', path, '-ac', str(ch), '-ar', str(sr), '-f', 'f32le', '-'],
                       capture_output=True, check=True).stdout
    return np.frombuffer(r, np.float32).astype(float).reshape(-1, ch)


def lag(x, ref, t0=20.0, t1=50.0, search=4.0, sr=SR):
    """Samples by which x runs behind ref (x[i + lag] lines up with ref[i]), from a 30 s window."""
    a = ref[int(t0 * sr):int(t1 * sr)].mean(1)
    b = x[int((t0 - search) * sr):int((t1 + search) * sr)].mean(1)
    c = fftconvolve(b, a[::-1], 'valid')
    return int(np.argmax(np.abs(c))) - int(search * sr)


def levels(x, hop=0.1, sr=SR):
    """dB RMS per hop of the mono sum."""
    m = x.mean(1) if x.ndim == 2 else x
    h = int(hop * sr)
    n = len(m) // h
    return 20 * np.log10(np.sqrt((m[:n * h].reshape(n, h) ** 2).mean(1)) + 1e-9)


def gain_fit(x, y):
    """g minimising |x - g y|, and the residual in dB relative to x."""
    g = float(x.ravel() @ y.ravel()) / float(y.ravel() @ y.ravel())
    r = x - g * y
    return g, 20 * np.log10(np.sqrt((r ** 2).mean()) / np.sqrt((x ** 2).mean()) + 1e-12)
