import numpy as np


def parse_word(self, w):
    (w,) = w
    return str(w)


def parse_string(self, s):
    return " ".join(s)


def parse_int(self, i):
    (i,) = i
    return int(i)


def parse_float(self, f):
    (f,) = f
    return float(f)


def parse_array(self, a):
    (a,) = a
    return np.array(a)
