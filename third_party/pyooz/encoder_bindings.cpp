#define PY_SSIZE_T_CLEAN
#include <Python.h>

#include <climits>
#include <cmath>
#include <cstddef>
#include <vector>

#include "ooz/dep/ooz/stdafx.h"
#include "ooz/dep/ooz/compr_kraken.h"

int CompressBlock_Kraken(uint8 *src_in, uint8 *dst_in, int src_size, int level,
                         const CompressOptions *compressopts, uint8 *src_window_base,
                         LRMCascade *lrm);

static PyObject *ooz_compress(PyObject *, PyObject *args) {
    const char *src_data = nullptr;
    Py_ssize_t src_len = 0;
    int level = 5;
    if (!PyArg_ParseTuple(args, "y#|i", &src_data, &src_len, &level)) {
        return nullptr;
    }
    if (src_len <= 0 || src_len > INT_MAX) {
        PyErr_SetString(PyExc_ValueError, "raw payload must fit in a non-empty int-sized buffer");
        return nullptr;
    }

    const size_t quanta = (static_cast<size_t>(src_len) + 0x3ffffU) / 0x40000U;
    const size_t capacity = static_cast<size_t>(src_len) + 1024U + 512U * quanta;
    std::vector<uint8> dst(capacity);
    const int written = CompressBlock_Kraken(
        reinterpret_cast<uint8 *>(const_cast<char *>(src_data)),
        dst.data(),
        static_cast<int>(src_len),
        level,
        nullptr,
        nullptr,
        nullptr);
    if (written <= 0 || static_cast<size_t>(written) > dst.size()) {
        PyErr_SetString(PyExc_RuntimeError, "Kraken compression failed");
        return nullptr;
    }
    return PyBytes_FromStringAndSize(reinterpret_cast<const char *>(dst.data()), written);
}

static PyMethodDef methods[] = {
    {"compress", ooz_compress, METH_VARARGS, "Compress a raw payload into a Kraken stream."},
    {nullptr, nullptr, 0, nullptr},
};

static PyModuleDef module = {
    PyModuleDef_HEAD_INIT,
    "ooz_encoder",
    "The pyooz-compatible Kraken encoder used for edited saves.",
    -1,
    methods,
};

PyMODINIT_FUNC PyInit_ooz_encoder(void) {
    return PyModule_Create(&module);
}
