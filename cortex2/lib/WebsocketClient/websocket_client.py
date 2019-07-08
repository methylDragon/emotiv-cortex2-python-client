"""
WebsocketClient Class
@author: methylDragon
                                   .     .
                                .  |\-^-/|  .
                               /| } O.=.O { |\
                              /´ \ \_ ~ _/ / `\
                            /´ |  \-/ ~ \-/  | `\
                            |   |  /\\ //\  |   |
                             \|\|\/-""-""-\/|/|/
                                     ______/ /
                                     '------'
                       _   _        _  ___
             _ __  ___| |_| |_ _  _| ||   \ _ _ __ _ __ _ ___ _ _
            | '  \/ -_)  _| ' \ || | || |) | '_/ _` / _` / _ \ ' \
            |_|_|_\___|\__|_||_\_, |_||___/|_| \__,_\__, \___/_||_|
                               |__/                 |___/
            -------------------------------------------------------
                           github.com/methylDragon

    Description:
    Asynchronous Python client interacting with generic websocket servers!

    Requires:
    Python 3.6 or above

CH3EERS!

"""

import asyncio
import websockets
import json
import logging
import string
import secrets
import ssl


class WebsocketClient():
    """Generalised asynchronous websocket Python client."""
    def __init__(self, url, ssl_context, check_response=False, response_key="id", timeout=10):
        if not ssl_context:
            self._ssl_context = ssl._create_unverified_context()
        else:
            self._ssl_context = ssl_context

        self._url = url
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)

        while self._loop.is_running():
            pass

        self._websocket = self._loop.run_until_complete(websockets.connect(url, ssl=self._ssl_context))
        self.last_request = None

        self.check_response = check_response
        self.response_key = response_key

        ## Logger Setup
        self.logger = logging.getLogger(self.__class__.__name__)
        self.logger.setLevel(logging.INFO)

        # Logger Handler Setup
        self.c_handler = logging.StreamHandler()
        self.c_handler.setLevel(logging.INFO)
        self.c_format = logging.Formatter('%(name)s - %(levelname)s: %(message)s')
        self.c_handler.setFormatter(self.c_format)

        # Logger Handler Binding
        self.logger.handlers.clear()
        self.logger.addHandler(self.c_handler)

        self.timeout = timeout

    def __del__(self):
        try:
            self.logger.info("Closing websocket...")
            self._websocket.close()
        except Exception as e:
            self.logger.error(str(e))

    # Public
    def flush_buffer(self, msgs_to_flush=10000):
        for i in range(msgs_to_flush):
            while self._loop.is_running():
                pass

            response = self._loop.run_until_complete(self._recv_data())
            if response is None:
                return
        return

    def send_request(self, method=None, params={}, request=None, loop=None):
        """Send request object and parse response."""
        if loop is None:
            loop = self._loop

        if not request: # If a request was explicitly passed in, use it instead
            assert method is not None, "No method specified!"
            request = self._create_request(method, params)

        self.last_request = request
        response = self._send_and_recv_data(request, loop)

        for i in range(10000):
            # Search extensively until a valid response key is found
            # This generally empties the callback queue
            if response is None:
                self.logger.error("No data received.")
                return

            if self._check_response(json.loads(request), response):
                error_flag, error_msg = self._check_error(response)

                if i > 0:
                    self.logger.info("%d non-response messages skipped.", i)

                return self._parse_response(error_flag, error_msg, response)
            else:
                while self._loop.is_running():
                    pass

                response = loop.run_until_complete(self._recv_data())

        self.logger.error("ID mismatch! Could not find response message.")
        return

    # Private
    async def _send_data(self, data):
        """Send data to websocket."""
        try:
            await asyncio.wait_for(self._websocket.send(data), timeout=self.timeout)
        except asyncio.TimeoutError:
            self.logger.warning("Asyncio Timeout: Sending took too long!")
        except:
            self.logger.error("Websocket connection broke! Reconnecting...")
            websockets.connect(self._url, ssl=self._ssl_context)
            await asyncio.sleep(1)

    async def _recv_data(self):
        """Receive data from websocket."""
        try:
            recv = await asyncio.wait_for(self._websocket.recv(), timeout=self.timeout)

            if type(recv) is str:
                return json.loads(recv)
            else:
                return
        except asyncio.TimeoutError:
            self.logger.warning("Asyncio Timeout: Receiving took too long!")
            return
        except Exception as e:
            self.logger.error("Websocket connection broke! Reconnecting...")
            self.logger.info(str(e))
            websockets.connect(self._url, ssl=self._ssl_context)
            await asyncio.sleep(1)

    def _send_and_recv_data(self, data, loop=None):
        """Send and receive data to and from websocket."""
        if loop is None:
            loop = self._loop

        while self._loop.is_running():
            pass

        loop.run_until_complete(self._send_data(data))
        return loop.run_until_complete(self._recv_data())

    def _generate_id(self, size=6, chars=string.ascii_letters+string.digits):
        """Generate random ID."""
        return ''.join(secrets.choice(chars) for _ in range(size))

    def _check_response(self, send_dict, response):
        """Check if response key matches."""
        if not self.check_response:
            return True

        try:
            if send_dict[self.response_key] == response[self.response_key]:
                return True
            else:
                return False
        except:
            return False

    def _check_error(self, response):
        if 'error' in response:
            return True, response['error']
        else:
            return False, ''

    def _parse_response(self, error_flag, error_msg, response):
        """Return error message, result, or full result."""
        if error_flag:
            return error_msg
        elif 'result' in response:
            return response['result']
        else:
            return response

    def _create_request(self, method, params={}):
        """Create request object."""
        if self.check_response:
            return json.dumps({'jsonrpc': '2.0', 'method': method,
                               'params': params, 'id': self._generate_id()})
        else:
            return json.dumps({'jsonrpc': '2.0', 'method': method, 'params': params})
