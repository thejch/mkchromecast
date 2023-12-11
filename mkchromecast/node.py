# This file is part of mkchromecast.
"""
These functions are used to get up the streaming server using node.

To call them:
    from mkchromecast.node import *
    name()
"""

import configparser as ConfigParser
import multiprocessing
import os
import pickle
import psutil
import time
import sys
import signal
import subprocess

import mkchromecast
from mkchromecast.audio_devices import inputint, outputint
import mkchromecast.colors as colors
from mkchromecast.cast import Casting
from mkchromecast.config import config_manager
import mkchromecast.messages as msg
from mkchromecast.preferences import ConfigSectionMap


def streaming(mkcc: mkchromecast.Mkchromecast):
    """
    Configuration files
    """
    config = ConfigParser.RawConfigParser()
    # Class from mkchromecast.config
    configurations = config_manager()
    configf = configurations.configf

    if os.path.exists(configf) and mkcc.tray is True:
        configurations.chk_config()
        print(colors.warning("Configuration file exists"))
        print(colors.warning("Using defaults set there"))
        config.read(configf)
        backend = ConfigSectionMap("settings")["backend"]
        rcodec = ConfigSectionMap("settings")["codec"]
        bitrate = ConfigSectionMap("settings")["bitrate"]
        samplerate = ConfigSectionMap("settings")["samplerate"]
        notifications = ConfigSectionMap("settings")["notifications"]
    else:
        backend = mkcc.backend
        rcodec = mkcc.rcodec
        codec = mkcc.codec
        bitrate = str(mkcc.bitrate)
        samplerate = str(mkcc.samplerate)
        notifications = mkcc.notifications

    print(colors.options("Selected backend:") + " " + backend)

    if mkcc.debug is True:
        print(
            ":::node::: variables %s, %s, %s, %s, %s"
            % (backend, rcodec, bitrate, samplerate, notifications)
        )

    if mkcc.youtube_url is None:
        if backend == "node" and rcodec != "mp3":
            print(
                colors.warning(
                    "Codec " + rcodec + " is not supported by the node server!"
                )
            )
            print("Using " + codec + " as default.")

        if backend == "node":
            if int(bitrate) == 192:
                print(colors.options("Default bitrate used:") + " " + bitrate + "k.")
            elif int(bitrate) > 500:
                print(
                    colors.warning("Maximum bitrate supported by " + codec + " is:")
                    + " "
                    + str(500)
                    + "k."
                )
                bitrate = "500"
                print(colors.warning("Bitrate has been set to maximum!"))
            else:
                print(colors.options("Selected bitrate: ") + bitrate + "k.")

            if samplerate == "44100":
                print(
                    colors.options("Default sample rate used:")
                    + " "
                    + samplerate
                    + "Hz."
                )
            else:
                # TODO(xsdg): This should really be elif codec in codecs_sr.
                codecs_sr = ["mp3", "ogg", "aac", "wav", "flac"]

                """
                The codecs below do not support 96000Hz
                """
                no96k = ["mp3", "ogg"]

                # TODO(xsdg): factor this out into a quantize_sample_rates
                # function that takes a codec and a sample rate.  Also, use
                # same from audio.py
                if (
                    codec in codecs_sr
                    and int(samplerate) > 22000
                    and int(samplerate) <= 27050
                ):
                    samplerate = "22050"
                    msg.print_samplerate_warning(mkcc, codec)

                if (
                    codec in codecs_sr
                    and int(samplerate) > 27050
                    and int(samplerate) <= 32000
                ):
                    samplerate = "32000"
                    msg.print_samplerate_warning(mkcc, codec)

                elif (
                    codec in codecs_sr
                    and int(samplerate) > 32000
                    and int(samplerate) <= 36000
                ):
                    samplerate = "32000"
                    msg.print_samplerate_warning(mkcc, codec)

                elif (
                    codec in codecs_sr
                    and int(samplerate) > 36000
                    and int(samplerate) <= 43000
                ):
                    samplerate = "44100"
                    msg.print_samplerate_warning(mkcc, codec)
                    print(
                        colors.warning(
                            "Sample rate has been set to default!"
                        )
                    )

                elif (
                    codec in codecs_sr
                    and int(samplerate) > 43000
                    and int(samplerate) <= 72000
                ):
                    samplerate = "48000"
                    msg.print_samplerate_warning(mkcc, codec)

                elif codec in codecs_sr and int(samplerate) > 72000:
                    # TODO(xsdg): This seems like it was supposed to alter the
                    # sample rate somehow, but it doesn't.
                    if codec in no96k:
                        samplerate = "48000"
                        msg.print_samplerate_warning(mkcc, codec)
                    print(
                        colors.warning(
                            "Sample rate has been set to maximum!"
                        )
                    )

                print(colors.options("Sample rate set to:") + " " + samplerate + "Hz.")

    """
    Node section
    """
    paths = ["/usr/local/bin/node", "./bin/node", "./nodejs/bin/node"]

    for path in paths:
        if os.path.exists(path) is True:
            webcast = [
                path,
                "./nodejs/node_modules/webcast-osx-audio/bin/webcast.js",
                "-b",
                bitrate,
                "-s",
                samplerate,
                "-p",
                "5000",
                "-u",
                "stream",
            ]
            break
    else:
        webcast = None
        print(colors.warning("Node is not installed..."))
        print(
            colors.warning("Use your package manager or their official " "installer...")
        )
        pass

    if webcast is not None:
        p = subprocess.Popen(webcast)

        if mkcc.debug is True:
            print(":::node::: node command: %s." % webcast)

        f = open("/tmp/mkchromecast.pid", "rb")
        pidnumber = int(pickle.load(f))
        print(colors.options("PID of main process:") + " " + str(pidnumber))

        localpid = os.getpid()
        print(colors.options("PID of streaming process: ") + str(localpid))

        while p.poll() is None:
            try:
                time.sleep(0.5)
                # With this I ensure that if the main app fails, everything
                # will get back to normal
                if psutil.pid_exists(pidnumber) is False:
                    inputint()
                    outputint()
                    parent = psutil.Process(localpid)
                    # or parent.children() for recursive=False
                    for child in parent.children(recursive=True):
                        child.kill()
                    parent.kill()
            except KeyboardInterrupt:
                print("Ctrl-c was requested")
                sys.exit(0)
            except IOError:
                print("I/O Error")
                sys.exit(0)
            except OSError:
                print("OSError")
                sys.exit(0)
        else:
            print(colors.warning("Reconnecting node streaming..."))
            if mkcc.platform == "Darwin" and notifications == "enabled":
                if os.path.exists("images/google.icns") is True:
                    noticon = "images/google.icns"
                else:
                    noticon = "google.icns"
            if mkcc.debug is True:
                print(
                    ":::node::: platform, tray, notifications: %s, %s, %s."
                    % (mkcc.platform, mkcc.tray, notifications)
                )

            if mkcc.platform == "Darwin" and mkcc.tray is True and notifications == "enabled":
                reconnecting = [
                    "./notifier/terminal-notifier.app/Contents/MacOS/terminal-notifier",
                    "-group",
                    "cast",
                    "-contentImage",
                    noticon,
                    "-title",
                    "mkchromecast",
                    "-subtitle",
                    "node server failed",
                    "-message",
                    "Reconnecting...",
                ]
                subprocess.Popen(reconnecting)

                if mkcc.debug is True:
                    print(
                        ":::node::: reconnecting notifier command: %s." % reconnecting
                    )
            relaunch(stream, recasting, kill)
        return


class multi_proc(object):
    def __init__(self):
        self._mkcc = mkchromecast.Mkchromecast()
        self.proc = multiprocessing.Process(target=streaming, args=(self._mkcc,))
        self.proc.daemon = False

    def start(self):
        self.proc.start()


def kill():
    pid = os.getpid()
    os.kill(pid, signal.SIGTERM)
    return


def relaunch(func1, func2, func3):
    func1()
    func2()
    func3()
    return


def recasting():
    mkcc = mkchromecast.Mkchromecast()
    start = Casting(mkcc)
    start.initialize_cast()
    start.get_devices()
    start.play_cast()
    return


def stream():
    st = multi_proc()
    st.start()
