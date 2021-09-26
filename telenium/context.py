# coding=utf-8
from __future__ import print_function

import unittest
import subprocess
import os
from telenium.client import TeleniumHttpClient
from time import time, sleep
from uuid import uuid4


class TeleniumContext(object):
    """Telenium context manager that handles opening and closing the client."""

    def __init__(self,
        url = None,
        process_start_timeout = 5,
        cmd_env = None,
        cmd_entrypoint = None,
        cmd_process = None,
    ):
        """
        Args:
            url (str): Telenium url to connect to
            process_start_timeout (int): Timeout of the process to start, in seconds
            cmd_env (dict): Environment variables that can be passed to the process
            cmd_entrypoint (list(str)): Entrypoint of the process
            cmd_process (list(str)): Command to start the process (cmd_entrypoint is appended to this)
        """
        host = os.environ.get("TELENIUM_HOST", "localhost")
        port = int(os.environ.get("TELENIUM_PORT", "9901"))
        self.url = url or "http://{}:{}/jsonrpc".format(host, port)
        self.process_start_timeout = process_start_timeout
        self.cmd_env = cmd_env or {}
        self.cmd_entrypoint = cmd_entrypoint or ["main.py"]
        self.cmd_process = cmd_process or ["python", "-m", "telenium.execute"]

    def __enter__(self):
        self.telenium_token = str(uuid4())
        self.cli = TeleniumHttpClient(url=self.url, timeout=5)

        # prior test, close any possible previous telenium application
        # to ensure this one might be executed correctly.
        try:
            self.cli.app_quit()
            sleep(2)
        except:
            pass

        # prepare the environment of the application to start
        env = os.environ.copy()
        env["TELENIUM_TOKEN"] = self.telenium_token
        for key, value in self.cmd_env.items():
            env[key] = str(value)
        cmd = self.cmd_process + self.cmd_entrypoint

        # start the application
        if os.environ.get("TELENIUM_TARGET", None) == "android":
            self.start_android_process(env=env)
        else:
            self.start_desktop_process(cmd=cmd, env=env)

        # wait for telenium server to be online
        start = time()
        while True:
            try:
                self.cli.ping()
                break
            except Exception:
                if time() - start > self.process_start_timeout:
                    raise Exception("timeout")
                sleep(1)

        # ensure the telenium we are connected are the same as the one we
        # launched here
        if self.cli.get_token() != self.telenium_token:
            raise Exception("Connected to another telenium server")

        return self

    def start_desktop_process(self, cmd, env):
        self.process = subprocess.Popen(cmd, env=env)

    def start_android_process(self, env):
        import subprocess
        import json
        package = os.environ.get("TELENIUM_ANDROID_PACKAGE", None)
        entry = os.environ.get("TELENIUM_ANDROID_ENTRY",
                               "org.kivy.android.PythonActivity")
        telenium_env = self.cmd_env.copy()
        telenium_env["TELENIUM_TOKEN"] = env["TELENIUM_TOKEN"]
        cmd = [
            "adb", "shell", "am", "start", "-n",
            "{}/{}".format(package, entry), "-a", entry
        ]

        filename = "/tmp/telenium_env.json"
        with open(filename, "w") as fd:
            fd.write(json.dumps(telenium_env))
        cmd_env = ["adb", "push", filename, "/sdcard/telenium_env.json"]
        print("Execute: {}".format(cmd_env))
        subprocess.Popen(cmd_env).communicate()
        print("Execute: {}".format(cmd))
        self.process = subprocess.Popen(cmd)
        print(self.process.communicate())

    def __exit__(self, exc_type, exc_value, traceback):
        try:
            self.cli.app_quit()
        except:
            pass  # app already closed
        self.process.wait()

    def assertExists(self, selector, timeout=-1):
        assert self.cli.wait(selector, timeout=timeout)

    def assertNotExists(self, selector, timeout=-1):
        start = time()
        while True:
            matches = self.cli.select(selector)
            if not matches:
                return True
            if timeout == -1:
                raise AssertionError("selector matched elements")
            if timeout > 0 and time() - start > timeout:
                raise Exception("Timeout")
            sleep(0.1)
