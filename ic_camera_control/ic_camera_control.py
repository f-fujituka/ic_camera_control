import os
import ctypes
import logging
import threading

import cv2
import numpy as np

from . import tisgrabber as tis

# ライブラリのルートロガーを作成
logger = logging.getLogger('ic_camera_control')
logger.addHandler(logging.NullHandler())


def configure_logging(level=logging.WARNING, handler=None):
    """ ライブラリのロガー設定を行う関数

    Args:
        level (int): ログレベル (e.g., logging.DEBUG, logging.INFO, etc.)
        handler (logging.Handler): ログ出力先のハンドラー (省略時はStreamHandler)
    """
    if handler is None:
        handler = logging.StreamHandler()

    handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    logger.addHandler(handler)
    logger.setLevel(level)


class CallbackUserdata(ctypes.Structure):
    """  コールバック関数に渡されるユーザーデータの例 """
    def __init__(self, ):
        self.unsused = ""
        self.devicename = ""
        self.connected = False


class IcCameraControl:
    def __init__(self, config_file_path="", IC_MsgBox_show=True, dll_path="./tisgrabber_x64.dll"):
        """ 単体カメラを表示するクラス

        Args:
            config_file_path(str): カメラのコンフィグファイルの場所
            dll_path(str): tisgrabber_x64.dllの場所
        """
        self._width = ctypes.c_long()  # 画像の幅
        self._height = ctypes.c_long()  # 画像の高さ
        self._bits_per_pixel = ctypes.c_int()  # ビット深度
        self._color_format = ctypes.c_int()  # カラーフォーマット
        self._channel = 0  # チャンネル数
        self._buffer_size = 0  # バッファサイズ

        # tisgrabber_x64.dllをインポート
        main_dir = os.path.dirname(os.path.abspath("__main__"))
        os.chdir(os.path.dirname(os.path.abspath(__file__)))
        self.ic = ctypes.cdll.LoadLibrary(dll_path)
        os.chdir(main_dir)
        tis.declareFunctions(self.ic)

        # ICImagingControlクラスライブラリを初期化
        self.ic.IC_InitLibrary(0)

        # ICのメッセージボックスを表示するフラグ
        self.IC_MsgBox_show = IC_MsgBox_show

        # 関数ポインタを作成
        self.frameReadyCallbackFunc = self.ic.FRAMEREADYCALLBACK(self._frameReadyCallback)
        self.userdata = CallbackUserdata()
        self.deviceLostCallbackFunc = self.ic.DEVICELOSTCALLBACK(self._deviceLostCallback)

        # 新しいグラバーハンドルを作成
        self._hGrabber = self.ic.IC_CreateGrabber()

        # デバイスを開く
        self.open_device(config_file_path)

        # 取得した画像をそのままnumpy配列に変換するとなぜか上下反転するので、反転させるフィルターを有効化しておく
        self._flip_image()

        # 取得開始
        self.start()

    @staticmethod
    def _frameReadyCallback(hGrabber, pBuffer, framenumber, pData):
        # コールバック関数処理
        # 省略
        return

    @staticmethod
    def _deviceLostCallback(hGrabber, userdata):
        """ このデバイスはコールバック関数を失いました。 カメラが切断された場合に呼び出されます。
        この関数は、メインスレッドではなく、別スレッドで実行されます。

        Args:
            hGrabber: これはグラバーオブジェクトへの実際のポインターです。（使用禁止）
            userdata: ユーザーデータ構造へのポインター
        """
        userdata.connected = False
        logger.error(f"Device {userdata.devicename} lost")

    @staticmethod
    def _handle_device_open_error():
        logger.info("No device opened")

    def read(self):
        """ 画像の取得

        Returns:
            (bool, img or None): (画像を取得できたかどうか, 3ch画像)

        """
        if self.ic.IC_SnapImage(self._hGrabber, -1) == tis.IC_SUCCESS:
            image_ptr = self.ic.IC_GetImagePtr(self._hGrabber)
            if image_ptr is not None:
                image_data = ctypes.cast(image_ptr, ctypes.POINTER(ctypes.c_ubyte * self._buffer_size))
                img_array = np.ndarray(buffer=image_data.contents, dtype=np.uint8,
                                       shape=(self._height.value, self._width.value, self._channel))
                return self.userdata.connected, img_array
            else:
                logger.warning("No device found.")
        else:
            return self.userdata.connected, None

    def open_device(self, config_file_path):
        """ デバイスを開く

        設定ファイルがある場合は、設定ファイルの情報を元に開く
        設定ファイルがなく2つ以上の接続がある場合はダイアログで選択する
        Args:
            config_file_path (str):***.xml 読み込むファイルの場所

        Returns:
            bool: 開くことができたか
        """
        self.load_properties(config_file_path, should_open_device=True)

        if not self.ic.IC_IsDevValid(self._hGrabber):  # 設定ファイルが存在しない場合にカメラを開く
            self._hGrabber = self._select_device()

        if self.ic.IC_IsDevValid(self._hGrabber):
            self._setup_device()
            logger.info(f"Device {self.userdata.devicename} open")
            return True
        else:
            self._handle_device_open_error()
            return False

    def load_properties(self, config_file_path, should_open_device=False):
        """ 設定ファイルのロード

        上手く読み込めなかったらエラーメッセージ
        設定ファイルを切り替える際もこの関数を使用する
        Args:
            config_file_path (str):***.xml 読み込むファイルの場所
            should_open_device (bool): OpenDeviceが 1 or 0

        """
        ret = self.ic.IC_LoadDeviceStateFromFileEx(self._hGrabber, tis.T(config_file_path), should_open_device)
        # 設定ファイルが存在しない場合、デバイスがない場合、xmlの形式が間違っている場合
        if ret == tis.IC_FILE_NOT_FOUND or ret == tis.IC_DEVICE_NOT_FOUND or ret == tis.IC_WRONG_XML_FORMAT or \
                ret == tis.IC_WRONG_INCOMPATIBLE_XML:
            logger.error("Can not load config")

    def start(self, create_window=False):
        """ 画像の取得の開始

        Args:
            create_window (bool): Trueだと、tisgrabberがウィンドウを生成してくれる
        """
        self.ic.IC_StartLive(self._hGrabber, create_window)

        # 画像の解像度・フォーマットを取得
        self._get_image_description()

    def release(self):
        """ 終了処理 """
        if self.ic.IC_IsDevValid(self._hGrabber):
            self.ic.IC_StopLive(self._hGrabber)
            self.ic.IC_ReleaseGrabber(self._hGrabber)

    def show_property_dialog(self):
        """ 設定変更ウィンドウを表示 """
        dialog_thread = threading.Thread(target=self.ic.IC_ShowPropertyDialog, args=(self._hGrabber,))
        dialog_thread.start()

    def list_available_properties(self):
        """設定可能な項目一覧を表示。なぜかライブ中だと表示できない。"""
        self.ic.IC_printItemandElementNames(self._hGrabber)

    def save_properties(self, file_path):
        """ 設定ファイルの保存。XML形式。

        Args:
            file_path (str): ***.xml 保存する場所

        """
        self.ic.IC_SaveDeviceStateToFile(self._hGrabber, tis.T(file_path))

    def _select_device(self):
        """ デバイスを選択または開く """
        devicecount = self.ic.IC_GetDeviceCount()
        if devicecount > 1:  # カメラが２つ以上ある場合はダイアログで選択
            return self.ic.IC_ShowDeviceSelectionDialog(None)
        else:
            unique_name = self.ic.IC_GetUniqueNamefromList(0)
            self.ic.IC_OpenDevByUniqueName(self._hGrabber, unique_name)  # カメラ接続
            return self._hGrabber

    def _setup_device(self):
        """ デバイスの設定 """
        self.userdata.devicename = self.ic.IC_GetDeviceName(self._hGrabber).decode('utf-8', 'ignore')
        self.userdata.connected = True

        self.ic.IC_SetCallbacks(self._hGrabber,
                                self.frameReadyCallbackFunc, None,
                                self.deviceLostCallbackFunc, self.userdata)

    def _flip_image(self):
        """ 画像を反転させる

        取得した画像をnumpy配列に変換するとなぜか上下反転されてるので、反転フィルターを事前に加える
        """
        _filter = tis.HFRAMEFILTER()
        self.ic.IC_CreateFrameFilter(tis.T("Rotate Flip"), _filter)
        self.ic.IC_AddFrameFilterToDevice(self._hGrabber, _filter)
        self.ic.IC_FrameFilterSetParameterBoolean(_filter, tis.T("Flip V"), 1)

    def _get_image_description(self):
        """ 画像の解像度・フォーマットを取得する """
        self.ic.IC_GetImageDescription(self._hGrabber,
                                       self._width, self._height, self._bits_per_pixel, self._color_format)
        self._channel = int(self._bits_per_pixel.value / 8.0)
        self._buffer_size = self._width.value * self._height.value * self._bits_per_pixel.value

    @property
    def width(self):
        """ 画像の幅 """
        return self._width.value

    @property
    def height(self):
        """ 画像の高さ """
        return self._height.value

    @property
    def userdate(self):
        """ カメラの情報 """
        return self.userdata


if __name__ == '__main__':
    config_file1 = ""
    config_file2 = ""

    cap = IcCameraControl(config_file1)

    cv2.namedWindow("img", cv2.WINDOW_NORMAL)
    cv2.resizeWindow("img", 1200, 900)

    print(cap.userdata.devicename)
    while True:
        ret_, img = cap.read()
        if not ret_:
            print("Camera is disconnected.")
            break
        cv2.imshow("img", img)
        k = cv2.waitKey(1)
        if k == 27:
            break
        elif k == ord("1"):  # 設定ファイルが切り替わる
            cap.load_properties(config_file1)
        elif k == ord("2"):  # 設定ファイルが切り替わる
            cap.load_properties(config_file2)
        elif k == ord("s"):
            cap.save_properties(config_file1)
        elif k == ord("a"):
            cap.show_property_dialog()
        elif k == ord("l"):
            cap.list_available_properties()

    cv2.destroyAllWindows()
    cap.release()
