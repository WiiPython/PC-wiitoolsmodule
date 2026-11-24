"""wiitools for PC.

Runs programs written for the ``wiitools`` module in the Wii CPython build
unchanged on a PC:

* Graphics (GX/XFB, PNG, shapes, 8x8 text, surfaces) -> numpy software renderer
  in a pygame window
* Wiimote/Nunchuk/Classic/GameCube controller -> keyboard, mouse, and gamepads
* SD/USB (``sd:/``, ``usb:/``) -> local folders (see ``wiitools._config``)
* Network/sockets -> host sockets, ``curl_*`` -> libcurl (pycurl)
* AUDIO -> pygame.mixer, ``c_run`` -> ctypes

The API matches ``wiitools.pyi`` (version 0.2).
"""
from __future__ import annotations

__version__ = "0.2"

from ._audio import (  # noqa: F401
    AUDIO_GetDMABytesLeft, AUDIO_GetDMAEnableFlag, AUDIO_GetDMAEvent, AUDIO_GetDMALength,
    AUDIO_GetDMAStartAddr, AUDIO_GetDSPSampleRate, AUDIO_Init, AUDIO_InitDMA,
    AUDIO_RegisterDMACallback, AUDIO_SetDSPSampleRate, AUDIO_StartDMA, AUDIO_StopDMA,
    audio_play_tone,
)
from ._curl import curl_download, curl_get, curl_post, curl_request  # noqa: F401
from ._fs import fatInitDefault, read_file, remove, write_file  # noqa: F401
from ._gfx import (  # noqa: F401
    VIDEO_WaitVSync, blit, draw_circle, draw_oval, draw_rect, gutil_prepare, height,
    input_update, png, png_info, png_load, png_load_embedded, png_load_embedded_named,
    png_load_named, png_quad, png_save, png_show, png_show_fullscreen, png_show_region,
    png_show_region_scaled, png_show_scaled, png_unload, png_unload_all, png_use,
    render_text, render_update, rendering_adopt, rendering_init, set_screen_size,
    surface_blit, surface_clear_target, surface_fill, surface_flip, surface_get_pixels,
    surface_get_size, surface_new, surface_rotate_90, surface_set_pixels, surface_set_target,
    terminal_init, text_length, update, usleep, width,
)
from ._net import (  # noqa: F401
    AF_INET, FIONBIO, IPPROTO_IP, IPPROTO_TCP, IPPROTO_UDP, O_NONBLOCK, PF_INET, POLLIN,
    POLLOUT, SO_REUSEADDR, SOCK_DGRAM, SOCK_STREAM, SOL_SOCKET, TCP_NODELAY, IsNetReady,
    get_local_ip, if_config, inet_addr, inet_aton, inet_ntoa, net_accept, net_bind,
    net_close, net_connect, net_deinit, net_fcntl, net_get_mac_address, net_get_status,
    net_gethostbyname, net_gethostip, net_getsockname, net_init, net_ioctl, net_listen,
    net_poll, net_read, net_recv, net_recvfrom, net_send, net_sendto, net_setsockopt,
    net_shutdown, net_socket, net_wc24cleanup, net_write,
)
from ._pad import (  # noqa: F401
    PAD_BUTTON_A, PAD_BUTTON_B, PAD_BUTTON_DOWN, PAD_BUTTON_LEFT, PAD_BUTTON_MENU,
    PAD_BUTTON_RIGHT, PAD_BUTTON_START, PAD_BUTTON_UP, PAD_BUTTON_X, PAD_BUTTON_Y,
    PAD_CHAN0, PAD_CHAN1, PAD_CHAN2, PAD_CHAN3, PAD_CHAN_ALL, PAD_CHANMAX, PAD_TRIGGER_L,
    PAD_TRIGGER_R, PAD_TRIGGER_Z, PAD_ButtonsDown, PAD_ButtonsHeld, PAD_ButtonsUp, PAD_Clamp,
    PAD_ControlMotor, PAD_GetSamplingEvent, PAD_Init, PAD_Read, PAD_Recalibrate, PAD_Reset,
    PAD_ScanPads, PAD_SetSamplingCallback, PAD_SetSpec, PAD_StickX, PAD_StickY,
    PAD_SubStickX, PAD_SubStickY, PAD_Sync, PAD_TriggerL, PAD_TriggerR,
)
from ._system import (  # noqa: F401
    CON_EnableGecko, CON_GetMetrics, CON_GetPosition, CONF_Get, CONF_GetArea,
    CONF_GetAspectRatio, CONF_GetCounterBias, CONF_GetDisplayOffsetH, CONF_GetEULA,
    CONF_GetEuRGB60, CONF_GetIdleLedMode, CONF_GetIRSensitivity, CONF_GetLanguage,
    CONF_GetLength, CONF_GetNickName, CONF_GetPadDevices, CONF_GetPadMotorMode,
    CONF_GetPadSpeakerVolume, CONF_GetParentalAnswer, CONF_GetParentalPassword,
    CONF_GetProgressiveScan, CONF_GetRegion, CONF_GetScreenSaverMode,
    CONF_GetSensorBarPosition, CONF_GetShutdownMode, CONF_GetSoundMode, CONF_GetType,
    CONF_GetVideo, CONF_GetWiiConnect24, CONF_Init, SYS_HOTRESET, SYS_POWEROFF,
    SYS_POWEROFF_IDLE, SYS_POWEROFF_STANDBY, SYS_RESTART, SYS_RETURNTOMENU, SYS_SHUTDOWN,
    SYS_CancelAlarm, SYS_CreateAlarm, SYS_GetAlarmEvent, SYS_GetArena1Size,
    SYS_GetArena2Size, SYS_GetCounterBias, SYS_GetDisplayOffsetH, SYS_GetEuRGB60,
    SYS_GetFontEncoding, SYS_GetGBSMode, SYS_GetHollywoodRevision, SYS_GetLanguage,
    SYS_GetPowerEvent, SYS_GetProgressiveScan, SYS_GetResetEvent, SYS_GetSoundMode,
    SYS_GetVideoMode, SYS_GetWirelessID, SYS_RemoveAlarm, SYS_Report, SYS_ResetButtonDown,
    SYS_ResetSystem, SYS_SetAlarm, SYS_SetCounterBias, SYS_SetDisplayOffsetH,
    SYS_SetEuRGB60, SYS_SetGBSMode, SYS_SetLanguage, SYS_SetPeriodicAlarm,
    SYS_SetPowerCallback, SYS_SetProgressiveScan, SYS_SetResetCallback, SYS_SetSoundMode,
    SYS_SetVideoMode, SYS_SetWirelessID, SYS_STDIO_Report, SYS_Time, WiiStdin, c_run, init,
    mem_free, terminal_print,
)
from ._types import (  # noqa: F401
    PADStatusDict, WPADClassicDict, WPADDataDict, WPADGuitarDict, WPADIRDict, WPADNunchukDict,
    WPADUnknownDict,
)
from ._wpad import (  # noqa: F401
    WPAD_BALANCE_BOARD, WPAD_BUTTON_1, WPAD_BUTTON_2, WPAD_BUTTON_A, WPAD_BUTTON_B,
    WPAD_BUTTON_DOWN, WPAD_BUTTON_HOME, WPAD_BUTTON_LEFT, WPAD_BUTTON_MINUS,
    WPAD_BUTTON_PLUS, WPAD_BUTTON_RIGHT, WPAD_BUTTON_UP, WPAD_CHAN_0, WPAD_CHAN_1,
    WPAD_CHAN_2, WPAD_CHAN_3, WPAD_CHAN_ALL, WPAD_CLASSIC_BUTTON_A, WPAD_CLASSIC_BUTTON_B,
    WPAD_CLASSIC_BUTTON_DOWN, WPAD_CLASSIC_BUTTON_FULL_L, WPAD_CLASSIC_BUTTON_FULL_R,
    WPAD_CLASSIC_BUTTON_HOME, WPAD_CLASSIC_BUTTON_LEFT, WPAD_CLASSIC_BUTTON_MINUS,
    WPAD_CLASSIC_BUTTON_PLUS, WPAD_CLASSIC_BUTTON_RIGHT, WPAD_CLASSIC_BUTTON_UP,
    WPAD_CLASSIC_BUTTON_X, WPAD_CLASSIC_BUTTON_Y, WPAD_CLASSIC_BUTTON_ZL,
    WPAD_CLASSIC_BUTTON_ZR, WPAD_DATA_BUTTONS, WPAD_GUITAR_HERO_3_BUTTON_BLUE,
    WPAD_GUITAR_HERO_3_BUTTON_GREEN, WPAD_GUITAR_HERO_3_BUTTON_MINUS,
    WPAD_GUITAR_HERO_3_BUTTON_ORANGE, WPAD_GUITAR_HERO_3_BUTTON_PLUS,
    WPAD_GUITAR_HERO_3_BUTTON_RED, WPAD_GUITAR_HERO_3_BUTTON_STRUM_DOWN,
    WPAD_GUITAR_HERO_3_BUTTON_STRUM_UP, WPAD_GUITAR_HERO_3_BUTTON_YELLOW,
    WPAD_MAX_WIIMOTES, WPAD_NUNCHUK_BUTTON_C, WPAD_NUNCHUK_BUTTON_Z,
    WPAD_THRESH_DEFAULT_BUTTONS, WPAD_Accel, WPAD_BatteryLevel, WPAD_ButtonsDown,
    WPAD_ButtonsDown_all, WPAD_ButtonsHeld, WPAD_ButtonsHeld_all, WPAD_ButtonsUp,
    WPAD_ButtonsUp_all, WPAD_ControlSpeaker, WPAD_Data, WPAD_Disconnect, WPAD_DroppedEvents,
    WPAD_EncodeData, WPAD_Expansion, WPAD_Flush, WPAD_GetBatteryDeadEvent,
    WPAD_GetPowerButtonEvent, WPAD_GetStatus, WPAD_GForce, WPAD_Init, WPAD_IR,
    WPAD_IsSpeakerEnabled, WPAD_Orientation, WPAD_Probe, WPAD_ReadEvent, WPAD_ReadPending,
    WPAD_Rumble, WPAD_ScanPads, WPAD_SendStreamData, WPAD_SetBatteryDeadCallback,
    WPAD_SetDataFormat, WPAD_SetEventBufs, WPAD_SetIdleThresholds, WPAD_SetIdleTimeout,
    WPAD_SetMotionPlus, WPAD_SetPowerButtonCallback, WPAD_SetVRes, WPAD_Shutdown,
    WPADState,
)

__all__ = [n for n in dir() if not n.startswith("_") and n != "annotations"]
