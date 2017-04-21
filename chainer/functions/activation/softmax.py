import numpy

import chainer
from chainer import cuda
from chainer import function
from chainer.utils import type_check

if cuda.cudnn_enabled:
    cudnn = cuda.cudnn
    libcudnn = cudnn.cudnn
    _cudnn_version = libcudnn.getVersion()
    _algorithm = libcudnn.CUDNN_SOFTMAX_ACCURATE
    _mode = libcudnn.CUDNN_SOFTMAX_MODE_CHANNEL


class Softmax(function.Function):

    """Softmax activation function."""

    def check_type_forward(self, in_types):
        type_check.expect(in_types.size() == 1)
        x_type, = in_types

        type_check.expect(
            x_type.dtype.kind == 'f',
            x_type.ndim > 1,
        )

    def forward(self, x):
        xp = cuda.get_array_module(*x)
        if (xp is not numpy and chainer.should_use_cudnn('>=auto') and
                (_cudnn_version >= 3000 or x[0].dtype != numpy.float16)):
            oz_dtype = 'd' if x[0].dtype == 'd' else 'f'
            one = numpy.array(1, dtype=oz_dtype).ctypes
            zero = numpy.array(0, dtype=oz_dtype).ctypes
            handle = cudnn.get_handle()
            x_cube = x[0].reshape(x[0].shape[:2] + (-1, 1))
            desc = cudnn.create_tensor_descriptor(x_cube)
            y = xp.empty_like(x[0])
            libcudnn.softmaxForward(
                handle, _algorithm, _mode, one.data, desc.value,
                x_cube.data.ptr, zero.data, desc.value,
                y.data.ptr)
        else:
            y = x[0] - x[0].max(axis=1, keepdims=True)
            xp.exp(y, out=y)
            y /= y.sum(axis=1, keepdims=True)

        self._x_xp = cuda.get_array_module(*x)
        self._x_shape = x[0].shape
        self._x_dtype = x[0].dtype
        self.retain_inputs(())
        self.retain_outputs((0,))
        return y,

    def backward(self, x, gy):
        y = self.output_data[0]
        xp = self._x_xp
        if (xp is not numpy and chainer.should_use_cudnn('>=auto') and
                (_cudnn_version >= 3000 or self._x_dtype != numpy.float16)):
            oz_dtype = 'd' if y[0].dtype == 'd' else 'f'
            one = numpy.array(1, dtype=oz_dtype).ctypes
            zero = numpy.array(0, dtype=oz_dtype).ctypes
            handle = cudnn.get_handle()
            gx = xp.empty(self._x_shape, dtype=self._x_dtype)
            gx_cube = gx.reshape(gx.shape[:2] + (-1, 1))
            desc = cudnn.create_tensor_descriptor(gx_cube)
            libcudnn.softmaxBackward(
                handle, _algorithm, _mode, one.data, desc.value,
                y.data.ptr, desc.value, gy[0].data.ptr, zero.data,
                desc.value, gx.data.ptr)
        else:
            gx = y * gy[0]
            sumdx = gx.sum(axis=1, keepdims=True)
            gx -= y * sumdx

        return gx,


def softmax(x):
    """Channelwise softmax function.

    This function computes its softmax along the second axis. Let
    :math:`x = (x_1, x_2, \\dots, x_d)^{\\top}` be the d dimensional index
    array and :math:`f(x)` be the d dimensional input array. For each index
    :math:`x` of the input array :math:`f(x)`, it computes the probability
    :math:`p(x)` defined as
    :math:`p(x) = {\\exp(f(x)) \\over \\sum_{x_2} \\exp(f(x))}`.

    Args:
        x (~chainer.Variable): Input variable.

    Returns:
        ~chainer.Variable: Output variable.

    """
    return Softmax()(x)
