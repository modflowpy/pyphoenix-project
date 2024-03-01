from flopy.utils.binaryfile import BinaryHeader
import numpy as np


# todo: clean this up to not need model information beyond grid_type,
#  shape, data header, data dtype, and filename, (optional, modelname,
#  pakname)
#  this is still a huge mess and needs a lot of cleanup to be an independent
#  module
class BinaryException(Exception):
    def __init__(self, *args):
        super.__init__(*args)

class BinaryArray():
    def __init__(self):
        self._pos = 0

    def read_binary_data_from_file(
        self,
        fname,
        data_shape,
        data_size,
        data_type,
        modelgrid,
        read_multi_layer=False,
    ):
        import flopy.utils.binaryfile as bf

        if not isinstance(modelgrid.ncpl, np.ndarray):
            if data_size != modelgrid.ncpl:
                read_multi_layer = True

        fd = _open_ext_file(fname, True)
        numpy_type, name = self.datum_to_numpy_type(data_type)
        header_dtype = bf.BinaryHeader.set_dtype(
            bintype=self._get_bintype(modelgrid), precision="double"
        )
        if read_multi_layer and len(data_shape) > 1:
            try:
                all_data = np.empty(data_shape, numpy_type)
                headers = []
                layer_shape = data_shape[1:]
                layer_data_size = int(data_size / data_shape[0])
                for index in range(0, data_shape[0]):
                    layer_data = self._read_binary_file_layer(
                        fd,
                        fname,
                        header_dtype,
                        numpy_type,
                        layer_data_size,
                        layer_shape,
                    )
                    all_data[index, :] = layer_data[0]
                    headers.append(layer_data[1])
                fd.close()
                return all_data, headers
            except BinaryException:
                fd.seek(self._pos, 0)
                bin_data = self._read_binary_file_layer(
                    fd, fname, header_dtype, numpy_type, data_size, data_shape
                )
                self._pos = fd.tell()
                fd.close()
                return bin_data
        else:
            bin_data = self._read_binary_file_layer(
                fd, fname, header_dtype, numpy_type, data_size, data_shape
            )
            fd.close()
            return bin_data

    def _get_header(
        self,
        modelgrid,
        modeltime,
        stress_period,
        precision,
        text,
        fname,
        ilay=None,
        data=None,
    ):
        # handle dis (row, col, lay), disv (ncpl, lay), and disu (nodes) cases
        if modelgrid is not None and modeltime is not None:
            pertim = modeltime.perlen[stress_period]
            totim = modeltime.perlen.sum()
            if ilay is None:
                ilay = modelgrid.nlay
            if modelgrid.grid_type == "structured":
                m1, m2, m3 = modelgrid.ncol, modelgrid.nrow, ilay
                if data is not None:
                    shape3d = modelgrid.nlay * modelgrid.nrow * modelgrid.ncol
                    if data.size == shape3d:
                        m1, m2, m3 = shape3d, 1, 1
                return BinaryHeader.create(
                    bintype="vardis",
                    precision=precision,
                    text=text,
                    m1=m1,
                    m2=m2,
                    m3=m3,
                    pertim=pertim,
                    totim=totim,
                    kstp=1,
                    kper=stress_period + 1,
                )
            elif modelgrid.grid_type == "vertex":
                if ilay is None:
                    ilay = modelgrid.nlay
                m1, m2, m3 = modelgrid.ncpl, 1, ilay
                if data is not None:
                    shape3d = modelgrid.nlay * modelgrid.ncpl
                    if data.size == shape3d:
                        m1, m2, m3 = shape3d, 1, 1
                return BinaryHeader.create(
                    bintype="vardisv",
                    precision=precision,
                    text=text,
                    m1=m1,
                    m2=m2,
                    m3=m3,
                    pertim=pertim,
                    totim=totim,
                    kstp=1,
                    kper=stress_period,
                )
            elif modelgrid.grid_type == "unstructured":
                m1, m2, m3 = modelgrid.nnodes, 1, 1
                return BinaryHeader.create(
                    bintype="vardisu",
                    precision=precision,
                    text=text,
                    m1=m1,
                    m2=1,
                    m3=1,
                    pertim=pertim,
                    totim=totim,
                    kstp=1,
                    kper=stress_period,
                )
            else:
                if ilay is None:
                    ilay = 1
                m1, m2, m3 = 1, 1, ilay
                header = BinaryHeader.create(
                    bintype="vardis",
                    precision=precision,
                    text=text,
                    m1=m1,
                    m2=m2,
                    m3=m3,
                    pertim=pertim,
                    totim=totim,
                    kstp=1,
                    kper=stress_period,
                )

        else:
            m1, m2, m3 = 1, 1, 1
            pertim = np.float64(1.0)
            header = BinaryHeader.create(
                bintype="vardis",
                precision=precision,
                text=text,
                m1=m1,
                m2=m2,
                m3=m3,
                pertim=pertim,
                totim=pertim,
                kstp=1,
                kper=stress_period,
            )

        return header

    def _write_layer(
        self,
        fd,
        data,
        modelgrid,
        modeltime,
        stress_period,
        precision,
        text,
        fname,
        ilay=None,
    ):
        header_data = self._get_header(
            modelgrid,
            modeltime,
            stress_period,
            precision,
            text,
            fname,
            ilay=ilay,
            data=data,
        )
        header_data.tofile(fd)
        data.tofile(fd)

    def _read_binary_file_layer(
        self, fd, fname, header_dtype, numpy_type, data_size, data_shape
    ):
        header_data = np.fromfile(fd, dtype=header_dtype, count=1)
        data = np.fromfile(fd, dtype=numpy_type, count=data_size)
        data = self._resolve_cellid_numbers_from_file(data)
        if data.size != data_size:
            message = (
                "Binary file {} does not contain expected data. "
                "Expected array size {} but found size "
                "{}.".format(fname, data_size, data.size)
            )
            type_, value_, traceback_ = sys.exc_info()
            raise BinaryException(
                self._data_dimensions.structure.get_model(),
                self._data_dimensions.structure.get_package(),
                self._data_dimensions.structure.path,
                "opening external file for writing",
                self.structure.name,
                inspect.stack()[0][3],
                type_,
                value_,
                traceback_,
                message,
                self._simulation_data.debug,
            )
        return data.reshape(data_shape), header_data

    def write_binary_file(
        self,
        data,
        fname,
        text,
        modelgrid=None,
        modeltime=None,
        stress_period=0,
        precision="double",
        write_multi_layer=False,
    ):
        data = self._resolve_cellid_numbers_to_file(data)
        fd = _open_ext_file(fname, binary=True, write=True)
        if data.size == modelgrid.nnodes:
            write_multi_layer = False
        if write_multi_layer:
            # write data from each layer with a separate header
            for layer, value in enumerate(data):
                self._write_layer(
                    fd,
                    value,
                    modelgrid,
                    modeltime,
                    stress_period,
                    precision,
                    text,
                    fname,
                    layer + 1,
                )
        else:
            # write data with a single header
            self._write_layer(
                fd,
                data,
                modelgrid,
                modeltime,
                stress_period,
                precision,
                text,
                fname,
            )
        fd.close()


class BinaryList():
    def __init__(self):
        pass

    def read_binary_data_from_file(
        self, read_file, modelgrid, precision="double", build_cellid=True
    ):
        # read from file
        header, int_cellid_indexes, ext_cellid_indexes = self._get_header(
            modelgrid, precision
        )
        file_array = np.fromfile(read_file, dtype=header, count=-1)
        if not build_cellid:
            return file_array
        # build data list for recarray
        cellid_size = len(self._get_cell_header(modelgrid))
        data_list = []
        for record in file_array:
            data_record = ()
            current_cellid_size = 0
            current_cellid = ()
            for index, data_item in enumerate(record):
                if index in ext_cellid_indexes:
                    current_cellid += (data_item - 1,)
                    current_cellid_size += 1
                    if current_cellid_size == cellid_size:
                        data_record += current_cellid
                        data_record = (data_record,)
                        current_cellid = ()
                        current_cellid_size = 0
                else:
                    data_record += (data_item,)
            data_list.append(data_record)
        return data_list

    def write_binary_file(
        self, data, fname, modelgrid=None, precision="double"
    ):
        fd = _open_ext_file(fname, binary=True, write=True)
        data_array = self._build_data_array(data, modelgrid, precision)
        data_array.tofile(fd)
        fd.close()

    def _get_cell_header(self, modelgrid):
        if modelgrid.grid_type == "structured":
            return [("layer", np.int32), ("row", np.int32), ("col", np.int32)]
        elif modelgrid.grid_type == "vertex":
            return [("layer", np.int32), ("ncpl", np.int32)]
        else:
            return [("nodes", np.int32)]


def _open_ext_file(fname, binary=False, write=False):
    model_dim = self._data_dimensions.package_dim.model_dim[0]
    read_file = self._simulation_data.mfpath.resolve_path(
        fname, model_dim.model_name
    )
    if write:
        options = "w"
    else:
        options = "r"
    if binary:
        options = f"{options}b"
    try:
        fd = open(read_file, options)
        return fd
    except:
        message = (
            "Unable to open file {} in mode {}.  Make sure the "
            "file is not locked and the folder exists"
            ".".format(read_file, options)
        )
        type_, value_, traceback_ = sys.exc_info()
        raise BinaryException(
            self._data_dimensions.structure.get_model(),
            self._data_dimensions.structure.get_package(),
            self._data_dimensions.structure.path,
            "opening external file for writing",
            self._data_dimensions.structure.name,
            inspect.stack()[0][3],
            type_,
            value_,
            traceback_,
            message,
            self._simulation_data.debug,
        )