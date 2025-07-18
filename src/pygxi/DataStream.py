#!/usr/bin/python
# -*- coding:utf-8 -*-
# -*-mode:python ; tab-width:4 -*- ex:set tabstop=4 shiftwidth=4 expandtab: -*-

import ctypes
import types
from typing import Any

import pygxi.Feature as feat
import pygxi.gxwrapper as gx

from .errors import InvalidCallError, ParameterTypeError
from .FeatureControl import FeatureControl
from .gxidef import UNSIGNED_INT_MAX, UNSIGNED_LONG_LONG_MAX
from .ImageProc import RawImage
from .status import check_return_status


class DataStream:
    def __init__(self, dev_handle, stream_handle) -> None:
        """
        :brief  Constructor for instance initialization
        :param dev_handle:      Device handle
        :param stream_handle:   Device Stream handle
        """
        self.__dev_handle = dev_handle

        self.__c_capture_callback = gx.CAP_CALL(self.__on_capture_callback)
        self.__py_capture_callback = None

        self.StreamAnnouncedBufferCount = feat.IntFeature(
            self.__dev_handle, gx.GxFeatureID.INT_ANNOUNCED_BUFFER_COUNT
        )
        self.StreamDeliveredFrameCount = feat.IntFeature(
            self.__dev_handle, gx.GxFeatureID.INT_DELIVERED_FRAME_COUNT
        )
        self.StreamLostFrameCount = feat.IntFeature(
            self.__dev_handle, gx.GxFeatureID.INT_LOST_FRAME_COUNT
        )
        self.StreamIncompleteFrameCount = feat.IntFeature(
            self.__dev_handle, gx.GxFeatureID.INT_INCOMPLETE_FRAME_COUNT
        )
        self.StreamDeliveredPacketCount = feat.IntFeature(
            self.__dev_handle, gx.GxFeatureID.INT_DELIVERED_PACKET_COUNT
        )
        self.StreamBufferHandlingMode = feat.EnumFeature(
            self.__dev_handle, gx.GxFeatureID.ENUM_STREAM_BUFFER_HANDLING_MODE
        )
        self.payload_size = 0
        self.acquisition_flag = False
        self.__data_stream_handle = stream_handle
        self.__stream_feature_control = FeatureControl(stream_handle)
        self.__frame_buf_map: dict[int, Any] = {}

    def get_feature_control(self) -> FeatureControl:
        """
        :brief      Get device stream feature control object
        :return:    Device stream feature control object
        """
        return self.__stream_feature_control

    def get_payload_size(self) -> int:
        """
        :brief      Get device stream payload size
        :return:    Payload size
        """
        status, stream_payload_size = gx.gx_get_payload_size(self.__data_stream_handle)
        check_return_status(status, "DataStreamHandle", "get_payload_size")
        return stream_payload_size

    def get_image(self, timeout=1000):
        """
        :brief          Get an image, get successfully create image class object
        :param          timeout:    Acquisition timeout, range:[0, 0xFFFFFFFF]
        :return:        image object
        """
        if not isinstance(timeout, int):
            raise ParameterTypeError(
                "DataStream.get_image: "
                "Expected timeout type is int, not %s" % type(timeout)
            )

        if (timeout < 0) or (timeout > UNSIGNED_INT_MAX):
            print(
                "DataStream.get_image: "
                "timeout out of bounds, minimum=0, maximum=%s"
                % hex(UNSIGNED_INT_MAX).__str__()
            )
            return None

        if self.acquisition_flag is False:
            print("DataStream.get_image: Current data steam don't  start acquisition")
            return None

        frame_data = gx.GxFrameData()
        frame_data.image_size = self.payload_size
        frame_data.image_buf = None
        image = RawImage(frame_data)

        status = gx.gx_get_image(self.__dev_handle, image.frame_data, timeout)
        if status == gx.GxStatusList.SUCCESS:
            return image
        elif status == gx.GxStatusList.TIMEOUT:
            return None
        else:
            check_return_status(status, "DataStream", "get_image")
            return None

    def dq_buf(self, timeout=1000):
        if not isinstance(timeout, int):
            raise ParameterTypeError(
                "DataStream.dq_buf: "
                "Expected timeout type is int, not %s" % type(timeout)
            )

        if (timeout < 0) or (timeout > UNSIGNED_INT_MAX):
            print(
                "DataStream.get_image: "
                "timeout out of bounds, minimum=0, maximum=%s"
                % hex(UNSIGNED_INT_MAX).__str__()
            )
            return None

        if not self.__py_capture_callback:
            raise InvalidCallError("Can't call DQBuf after register capture callback")

        if not self.acquisition_flag:
            print("DataStream.get_image: Current data steam don't  start acquisition")
            return None

        ptr_frame_buffer = ctypes.POINTER(gx.GxFrameBuffer)()
        status = gx.gx_dq_buf(
            self.__dev_handle, ctypes.byref(ptr_frame_buffer), timeout
        )
        if status == gx.GxStatusList.SUCCESS:
            frame_buffer = ptr_frame_buffer.contents
            self.__frame_buf_map[frame_buffer.buf_id] = ptr_frame_buffer
            frame_data = gx.GxFrameData()
            frame_data.status = frame_buffer.status
            frame_data.image_buf = frame_buffer.image_buf
            frame_data.width = frame_buffer.width
            frame_data.height = frame_buffer.height
            frame_data.pixel_format = frame_buffer.pixel_format
            frame_data.image_size = frame_buffer.image_size
            frame_data.frame_id = frame_buffer.frame_id
            frame_data.timestamp = frame_buffer.timestamp
            frame_data.buf_id = frame_buffer.buf_id

            image = RawImage(frame_data)
            return image
        elif status == gx.GxStatusList.TIMEOUT:
            return None
        else:
            check_return_status(status, "DataStream", "dq_buf")
            return None

    def q_buf(self, image):
        if not isinstance(image, RawImage):
            raise ParameterTypeError(
                "DataStream.q_buf: "
                "Expected image type is RawImage, not %s" % type(image)
            )

        if self.acquisition_flag is False:
            print("DataStream.get_image: Current data steam don't  start acquisition")
            return

        if not self.__py_capture_callback:
            raise InvalidCallError("Can't call DQBuf after register capture callback")

        ptr_frame_buffer = ctypes.POINTER(gx.GxFrameBuffer)()
        try:
            ptr_frame_buffer = self.__frame_buf_map[image.frame_data.buf_id]
        except KeyError:
            print(f"Key {image.frame_data.buf_id} not found in frame buffer map.")
            return

        status = gx.gx_q_buf(self.__dev_handle, ptr_frame_buffer)
        check_return_status(status, "DataStream", "q_buf")
        self.__frame_buf_map.pop(image.frame_data.buf_id)

    def flush_queue(self):
        status = gx.gx_flush_queue(self.__dev_handle)
        check_return_status(status, "DataStream", "flush_queue")

    def set_acquisition_flag(self, flag: bool) -> None:
        self.acquisition_flag = flag

    def set_acquisition_buffer_number(self, buf_num):
        """
        :brief      set the number of acquisition buffer
        :param      buf_num:   the number of acquisition buffer, range:[1, 0xFFFFFFFF]
        """
        if not isinstance(buf_num, int):
            raise ParameterTypeError(
                "DataStream.set_acquisition_buffer_number: "
                "Expected buf_num type is int, not %s" % type(buf_num)
            )

        if (buf_num < 1) or (buf_num > UNSIGNED_LONG_LONG_MAX):
            print(
                "DataStream.set_acquisition_buffer_number:"
                "buf_num out of bounds, minimum=1, maximum=%s"
                % hex(UNSIGNED_LONG_LONG_MAX).__str__()
            )
            return

        status = gx.gx_set_acquisition_buffer_number(self.__dev_handle, buf_num)
        check_return_status(status, "DataStream", "set_acquisition_buffer_number")

    def register_capture_callback(self, callback_func):
        """
        :brief      Register the capture event callback function.
        :param      callback_func:  callback function
        :return:    none
        """
        if not isinstance(callback_func, types.FunctionType):
            raise ParameterTypeError(
                "DataStream.register_capture_callback: "
                "Expected callback type is function not %s" % type(callback_func)
            )

        status = gx.gx_register_capture_callback(
            self.__dev_handle, self.__c_capture_callback
        )
        check_return_status(status, "DataStream", "register_capture_callback")

        # callback will not recorded when register callback failed.
        self.__py_capture_callback = callback_func

    def unregister_capture_callback(self):
        """
        :brief      Unregister the capture event callback function.
        :return:    none
        """
        status = gx.gx_unregister_capture_callback(self.__dev_handle)
        check_return_status(status, "DataStream", "unregister_capture_callback")
        self.__py_capture_callback = None

    def __on_capture_callback(self, capture_data):
        """
        :brief      Capture event callback function with capture date.
        :return:    none
        """
        frame_data = gx.GxFrameData()
        frame_data.image_buf = capture_data.contents.image_buf
        frame_data.width = capture_data.contents.width
        frame_data.height = capture_data.contents.height
        frame_data.pixel_format = capture_data.contents.pixel_format
        frame_data.image_size = capture_data.contents.image_size
        frame_data.frame_id = capture_data.contents.frame_id
        frame_data.timestamp = capture_data.contents.timestamp
        frame_data.status = capture_data.contents.status
        image = RawImage(frame_data)
        self.__py_capture_callback(image)


class U3VDataStream(DataStream):
    def __init__(self, dev_handle, stream_handle):
        self.__handle = dev_handle
        DataStream.__init__(self, self.__handle, stream_handle)
        self.StreamTransferSize = feat.IntFeature(
            self.__handle, gx.GxFeatureID.INT_STREAM_TRANSFER_SIZE
        )
        self.StreamTransferNumberUrb = feat.IntFeature(
            self.__handle, gx.GxFeatureID.INT_STREAM_TRANSFER_NUMBER_URB
        )
        self.StopAcquisitionMode = feat.EnumFeature(
            self.__handle, gx.GxFeatureID.ENUM_STOP_ACQUISITION_MODE
        )


class GEVDataStream(DataStream):
    def __init__(self, dev_handle, stream_handle):
        self.__handle = dev_handle
        DataStream.__init__(self, self.__handle, stream_handle)
        self.StreamResendPacketCount = feat.IntFeature(
            self.__handle, gx.GxFeatureID.INT_RESEND_PACKET_COUNT
        )
        self.StreamRescuedPacketCount = feat.IntFeature(
            self.__handle, gx.GxFeatureID.INT_RESCUED_PACKET_COUNT
        )
        self.StreamResendCommandCount = feat.IntFeature(
            self.__handle, gx.GxFeatureID.INT_RESEND_COMMAND_COUNT
        )
        self.StreamUnexpectedPacketCount = feat.IntFeature(
            self.__handle, gx.GxFeatureID.INT_UNEXPECTED_PACKET_COUNT
        )
        self.MaxPacketCountInOneBlock = feat.IntFeature(
            self.__handle, gx.GxFeatureID.INT_MAX_PACKET_COUNT_IN_ONE_BLOCK
        )
        self.MaxPacketCountInOneCommand = feat.IntFeature(
            self.__handle, gx.GxFeatureID.INT_MAX_PACKET_COUNT_IN_ONE_COMMAND
        )
        self.ResendTimeout = feat.IntFeature(
            self.__handle, gx.GxFeatureID.INT_RESEND_TIMEOUT
        )
        self.MaxWaitPacketCount = feat.IntFeature(
            self.__handle, gx.GxFeatureID.INT_MAX_WAIT_PACKET_COUNT
        )
        self.ResendMode = feat.EnumFeature(
            self.__handle, gx.GxFeatureID.ENUM_RESEND_MODE
        )
        self.StreamMissingBlockIDCount = feat.IntFeature(
            self.__handle, gx.GxFeatureID.INT_MISSING_BLOCK_ID_COUNT
        )
        self.BlockTimeout = feat.IntFeature(
            self.__handle, gx.GxFeatureID.INT_BLOCK_TIMEOUT
        )
        self.MaxNumQueueBuffer = feat.IntFeature(
            self.__handle, gx.GxFeatureID.INT_MAX_NUM_QUEUE_BUFFER
        )
        self.PacketTimeout = feat.IntFeature(
            self.__handle, gx.GxFeatureID.INT_PACKET_TIMEOUT
        )
        self.SocketBufferSize = feat.IntFeature(
            self.__handle, gx.GxFeatureID.INT_SOCKET_BUFFER_SIZE
        )
