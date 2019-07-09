"""
EmotivCortex2Client Class
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
    Python client for the Emotiv EEG Cortex 2 API.

    API Reference: https://emotiv.gitbook.io/cortex-api/

    Features the entire JSON-RPC API communicated via asynchronous websockets.
    The Cortex 2 app is used to host a websocket web server gateway interface
    that takes JSON requests and returns JSON data.

    This Python client is designed to be a wrapper client for said API.
    It streams multi-session sensor data using a separate asynchronous thread!

    Requires:
    Python 3.6 or above

CH3EERS!

"""

from .lib import WebsocketClient

from collections import deque, OrderedDict
from threading import Thread, Event
import signal
import logging
import time
import os


class EmotivCortex2Client(WebsocketClient):
    """
    Python client for the Emotiv EEG Cortex 2 API.

    API Reference: https://emotiv.gitbook.io/cortex-api/

    Features the entire JSON-RPC API communicated via asynchronous websockets.
    The Cortex 2 app is used to host a websocket web server gateway interface
    that takes JSON requests and returns JSON data.

    This Python client is designed to be a wrapper client for said API.
    """
    def __del__(self):
        self.logger.info("Destructor called: Cleaning up EmotivCortex2Client...")
        self.stop_subscriber()

        super().__del__()

    def __init__(self,
                 url,
                 ssl_context=None,
                 check_response=True,
                 client_id=None,
                 client_secret=None,
                 authenticate=False,
                 data_deque_size=10,
                 debug=False):

        print('''
 ______________________________________________
< Friendly reminder to turn on your Emotiv App! >
 ----------------------------------------------
                o
                 o  .     .  !
                 .  |\\-^-/|  .
                /| } O.=.O { |\\
''')

        # Explicit call to the WebsocketClient constructor for clarity
        super().__init__(url, ssl_context, check_response, response_key="id", timeout=10)

        # Wait to open
        while self._websocket.state != 1:
            print("Waiting for websocket to connect...")
            time.sleep(1)

        # Give time for websocket to bind
        for i in range(3):
            print("EmotivCortex2Client Initialising", " . " * (i + 1), end="\r")
            time.sleep(0.5)

        print()

        self.debug = debug

        ## Auth attributes
        self.client_id = client_id
        self.client_secret = client_secret
        self.cortex_token = None

        self.approved = False
        self.authorized = False

        ## Headset attributes
        # OrderedDict used for backwards compatibility
        self.headsets = OrderedDict()
        self.connected_headsets = OrderedDict()

        ## Session Attributes
        self.sessions = OrderedDict() # {session_id: session_data, ...}

        ## Data subscription attributes
        # Docs: https://emotiv.gitbook.io/cortex-api/data-subscription/data-sample-object
        self.data_deque_size = data_deque_size

        # All sensor data streams are keyed by session
        self.data_streams = {} # {session_id: {data_stream_deques_types: [data]}, ...}
        self.subscribed_streams = {} # {session_id: {stream_names: info}, ...}

        self.subscriber_thread = None
        self.stop_subscriber_flag = False # Thread stop flag

        # True if subscriber thread is active
        self.subscriber_spinning = False

        self.subscriber_messages_handled = 0

        # Event flag for blocking the subscriber from reading
        # If set, the subscriber will read, if cleared, subscriber will pause
        self.subscriber_reading = Event()
        self.subscriber_reading.set()
        # self._subscriber_loop = None

        ## Logger Setup
        self.logger = logging.getLogger(self.__class__.__name__)
        self.logger.setLevel(logging.INFO)

        # Logger Handler Setup
        self.c_handler = logging.StreamHandler()
        self.c_handler.setLevel(logging.INFO)
        self.c_format = logging.Formatter('%(name)s - %(levelname)s: %(message)s')
        self.c_handler.setFormatter(self.c_format)

        self.e_handler = logging.StreamHandler()
        self.e_handler.setLevel(logging.ERROR)
        self.e_format = logging.Formatter('ERROR OCCURED AT: EmotivCortex2Client - %(funcName)s - %(lineno)d')
        self.e_handler.setFormatter(self.e_format)

        # Logger Handler Binding
        self.logger.handlers.clear()
        self.logger.addHandler(self.c_handler)
        self.logger.addHandler(self.e_handler)

        # Register Exit Handlers
        self.interrupted = False
        for sig in (signal.SIGABRT, signal.SIGBREAK, signal.SIGINT, signal.SIGTERM):
            signal.signal(sig, self._exit_handler)

        # Run optional authentication
        if authenticate:
            print("Authenticating... This should take about 10 seconds")
            for i in range(3):
                self.authenticate()

                if self.approved and self.authorized:
                    break

        if not self.approved or not self.authorized:
            self.logger.warning("Client not authorized! Run authenticate() to authorize.")

        self.timeout = 1

        self.logger.info("EmotivCortex2Client Initialised!")

    ############################################################################
    # CLASS HELPERS
    ############################################################################

    def send_authed_request(self, method=None, params={}, request=None):
        """
        Helper method for reauthenticating before sending request.

        Use self.send_authed_request() for requests that require authentication
        Use self.send_request() if not
        """
        try:
            response = self.send_request(method, params, request)
        except Exception as e:
            self.logger.error(str(e))
            return {'code': -1337, 'message': "EMOTIVCORTEX2 PYTHON CLIENT ERROR: Auth Request Failed"}

        try:
            if type(response) is dict:
                code = response.get('code')

                if code is None:
                    return response
                elif code < 0:
                    self.authenticate()
                    params['cortexToken'] = self.cortex_token
                    response = self.send_request(method, params, request)
                    code = response.get('code')

                    if code < 0:
                        self.generate_new_token()
                        params['cortexToken'] = self.cortex_token
                        response = self.send_request(method, params, request)
                        code = response.get('code')

                if code < 0:
                    self.logger.error("Auth Request failed, could not reauthenticate. Aborting!")
                    self.logger.info("Message: %s", response['message'])
            else:
                return response
        except Exception as e:
            self.logger.error(str(e))

        return response

    def send_request(self, method=None, params={}, request=None):
        """Wrapper method for base send_request method."""
        try:
            # If the subscriber is reading, pause it, send response, then resume
            try:
                if self.subscriber_reading.is_set():
                    self.subscriber_reading.clear()

                    while self._loop.is_running():
                        pass

                    response = super().send_request(method, params, request)

                    self.subscriber_reading.set()
                else:
                    response = super().send_request(method, params, request)
            except Exception as e:
                self.logger.error(str(e))
                return {'code': -1337, 'message': "EMOTIVCORTEX2 PYTHON CLIENT ERROR: Request Failed"}
            return response
        except Exception as e:
            self.logger.error(str(e))
            return {'code': -1337, 'message': "EMOTIVCORTEX2 PYTHON CLIENT ERROR: Request Failed"}

    def set_client_id(self, client_id):
        self.client_id = client_id

    def set_client_secret(self, client_secret):
        self.client_secret = client_secret

    def _verify_key(self, key, response, field=None):
        """Try-Except wrapped helper function for key verification."""
        try:
            if response.get(key) is field:
                return True
            else:
                if type(field) == str:
                    if field in response.get(key):
                        return True
                return False
        except:
            if field is None:  # Returns True since None has no .get()
                return True
            else:
                return False

    def _exit_handler(self, _signo, _stack_frame):
        self.interrupted = True
        self.subscriber_reading.clear()
        self.stop_subscriber_flag = True
        self.logger.info("KILLING SCRIPT")
        os._exit(0)

    ############################################################################
    # CONNECTING TO CORTEX API
    ############################################################################

    def get_cortex_info(self):
        return self.send_request(method="getCortexInfo")

    ############################################################################
    # AUTHENTICATION
    ############################################################################

    def get_user_login(self):
        return self.send_request(method="getUserLogin")

    def request_access(self):
        for i in range(5):
            params = {'clientId': self.client_id,
                      'clientSecret': self.client_secret}

            response = self.send_request(method="requestAccess", params=params)

            if not self._verify_key('accessGranted', response, None):
                self.approved = True
                return response
            else:
                self.logger.warning("PLEASE APPROVE THE APP ON THE EMOTIV CORTEX APP!")
                time.sleep(0.5)

    def has_access_right(self):
        return self.send_request(method="hasAccessRight")

    def authorize(self):
        if self.authorized:
            return

        params = {'clientId': self.client_id,
                  'clientSecret': self.client_secret}

        response = self.send_request(method="authorize", params=params)

        if self._verify_key('cortexToken', response, None):
            self.logger.error("Could not authorize!")
            return response

        self.cortex_token = response['cortexToken']
        self.authorized = True
        return response

    def generate_new_token(self):
        params = {'clientId': self.client_id,
                  'clientSecret': self.client_secret,
                  'cortexToken': self.cortex_token}

        response = self.send_request(method="generateNewToken", params=params)

        if self._verify_key('cortexToken', response, None):
            self.logger.error("Could not generate new token.")
            return response

        self.cortex_token = response['cortexToken']
        self.authorized = True
        return response

    def get_user_information(self):
        params = {'cortexToken': self.cortex_token}

        response = self.send_authed_request(method="getUserInformation", params=params)
        return response

    def get_license_info(self):
        params = {'cortexToken': self.cortex_token}

        response = self.send_authed_request(method="getLicenseInfo", params=params)
        return response

    ## Helper Methods

    def authenticate(self):
        if self.approved and self.authorized:
            self.logger.info("Already authenticated!")
            return {'cortexToken': self.cortex_token}

        a = self.request_access()
        b = self.authorize()

        if a and b:
            return a, b
        else:
            # self.logger.info("Request Access: %s", str(a))
            # self.logger.info("Cortex Token: %s", str(b))
            if a is None and b is None:
                self.logger.error("Could not authenticate!")

    ############################################################################
    # HEADSETS
    ############################################################################

    def query_headsets(self, id=None, sync=True):
        self.refresh_headsets()

        if id is None:
            response = self.send_request(method="queryHeadsets")
            if sync:
                self.sync_headsets(response, query=False)
        else:
            response = self.send_request(method="queryHeadsets", params={'id': id})
            if sync:
                self.sync_headsets(query=False)

        return response

    def control_device(self, command, headset_id=None, mappings=None):
        """General headset controlling method."""
        params = {'command': command}

        if headset_id is not None:
            params['headset'] = headset_id
        if mappings is not None:
            params['mappings'] = mappings

        return self.send_request(method="controlDevice", params=params)

    def refresh_headsets(self):
        return self.send_request(method="controlDevice", params={'command': 'refresh'})

    def connect_headset(self, headset_id_idx=0, headset_id=None, mappings=None):
        if len(self.headsets) == 0:
            self.sync_headsets()

        if headset_id_idx != 0 and headset_id is not None:
            self.logger.error("Invalid request: Both headset ID index and headset id provided! Aborting.")
            return

        if headset_id is None:
            headset_id = list(self.headsets)[headset_id_idx]
            self.logger.info("Connecting: %s", str(headset_id))

        if mappings is None:
            params = {'command': 'connect',
                      'headset': headset_id}
        else:
            params = {'command': 'connect',
                      'headset': headset_id,
                      'mappings': mappings}

        # Retry several times before giving up
        for i in range(3):
            response = self.send_request(method="controlDevice", params=params)
            self.sync_headsets()
            time.sleep(1)

            if headset_id in list(self.connected_headsets):
                self.logger.info("HEADSET %s connected!", str(list(self.headsets).index(headset_id)))
                self.logger.info("ID: %s", str(headset_id))
                return response
            else:
                self.logger.info("Retrying... %d", i)

        self.logger.error("COULD NOT CONNECT!")
        return response

    def disconnect_headset(self, headset_id):
        params = {'command': 'disconnect',
                  'headset': headset_id}

        response = self.send_request(method="controlDevice", params=params)
        self.sync_headsets()

        return response

    def update_headset(self, settings, headset_id_idx=0, headset_id=None):
        if len(self.headsets) == 0:
            self.sync_headsets()

        if headset_id_idx != 0 and headset_id is not None:
            self.logger.error("Invalid request: Both headset ID index and headset id provided! Aborting.")
            return

        if headset_id is None:
            headset_id = list(self.headsets)[headset_id_idx]
            self.logger.info("Connecting: %s", str(headset_id))

        assert self.connected_headsets.get(headset_id) is not None, "Headset is not connected!"
        assert self._get_headset_type(headset_id) == "EPOCPLUS", "Method supported by EPOC+ only!"
        assert self.connected_headsets[headset_id]['connectedBy'] == "usb cable", "Method supported only on wired connection only!"

        params = {'cortexToken': self.cortex_token,
                  'headset': headset_id,
                  'setting': settings}

        return self.send_authed_request(method="updateHeadset", params=params)

    def maximize_headset(self, headset_id_idx=0, headset_id=None):
        if len(self.headsets) == 0:
            self.sync_headsets()

        if headset_id_idx != 0 and headset_id is not None:
            self.logger.error("Invalid request: Both headset ID index and headset id provided! Aborting.")
            return

        if headset_id is None:
            headset_id = list(self.headsets)[headset_id_idx]
            self.logger.info("Connecting: %s", str(headset_id))

        settings = {'mode': 'EPOCPLUS',
                    'eegRate': 256,
                    'memsRate': 128}

        self.update_headset(settings, headset_id=headset_id)

    def maximize_headset_no_motion(self, headset_id_idx=0, headset_id=None):
        if len(self.headsets) == 0:
            self.sync_headsets()

        if headset_id_idx != 0 and headset_id is not None:
            self.logger.error("Invalid request: Both headset ID index and headset id provided! Aborting.")
            return

        if headset_id is None:
            headset_id = list(self.headsets)[headset_id_idx]
            self.logger.info("Connecting: %s", str(headset_id))

        settings = {'mode': 'EPOCPLUS',
                    'eegRate': 256,
                    'memsRate': 0}

        self.update_headset(settings, headset_id=headset_id)

    ## Helper Methods

    def sync_headsets(self, response=None, query=True):
        if response is None:
            if query:
                response = self.query_headsets(sync=False)

        if type(response) == list:
            # Update seen headset OrderedDicts
            self.headsets.clear()
            self.connected_headsets.clear()

            for headset in response:
                self.headsets[headset['id']] = headset

                if headset['status'] == "connected":
                    self.connected_headsets[headset['id']] = headset
            self.logger.info("Headsets synced!")
        else:
            self.logger.error("Could not query headsets!")

    def _get_headset_type(self, headset_id):
        return headset_id.split("-")[0]

    ############################################################################
    # SESSIONS
    ############################################################################

    def create_session(self, headset_id_idx=0, headset_id=None):
        if len(self.headsets) == 0:
            self.sync_headsets()

        if headset_id_idx != 0 and headset_id is not None:
            self.logger.error("Invalid request: Both headset ID index and headset id provided! Aborting.")
            return

        if headset_id is None:
            headset_id = list(self.headsets)[headset_id_idx]
            self.logger.info("Creating session for: %s", headset_id)

        params = {'cortexToken': self.cortex_token,
                  'headset': headset_id,
                  'status': 'open'}

        response = self.send_authed_request(method="createSession", params=params)

        try:
            if self._verify_key('id', response, None):
                self.logger.error("Could not create session.")
            else:
                session_id = response.get('id')
                self._create_data_streams(session_id)

                self.logger.info("Session created: %s", session_id)
        except:
            self.logger.error("Could not create session.")

        self.sync_sessions()
        return response

    def create_activated_session(self, headset_id_idx=0, headset_id=None):
        """
        Start an activated session.

        Activated sessions are license-activated sessions that allow for raw
        EEG data and higher resolution data.
        """
        if len(self.headsets) == 0:
            self.sync_headsets()

        if headset_id_idx != 0 and headset_id is not None:
            self.logger.error("Invalid request: Both headset ID index and headset id provided! Aborting.")
            return

        if headset_id is None:
            headset_id = list(self.headsets)[headset_id_idx]
            self.logger.info("Creating activated session for: %s", headset_id)

        params = {'cortexToken': self.cortex_token,
                  'headset': headset_id,
                  'status': 'active'}

        response = self.send_authed_request(method="createSession", params=params)

        try:
            if self._verify_key('id', response, None):
                self.logger.error("Could not create session.")
            else:
                session_id = response.get('id')
                self._create_data_streams(session_id)

                self.logger.info("Session created: %s", session_id)
        except:
            self.logger.error("Could not create session.")

        self.sync_sessions()
        return response

    def update_session(self, status, session_id_idx=0, session_id=None):
        """General session updating method."""
        if session_id_idx != 0 and session_id is not None:
            self.logger.error("Invalid request: Both session ID index and session id provided! Aborting.")
            return

        if session_id is None:
            session_id = list(self.sessions)[session_id_idx]
            self.logger.info("Activating session %d: %s", session_id_idx, session_id)

        params = {'cortexToken': self.cortex_token,
                  'session': session_id,
                  'status': status}

        return self.send_authed_request(method="updateSession", params=params)

    def activate_session(self, session_id_idx=0, session_id=None):
        if session_id_idx != 0 and session_id is not None:
            self.logger.error("Invalid request: Both session ID index and session id provided! Aborting.")
            return

        if session_id is None:
            session_id = list(self.sessions)[session_id_idx]
            self.logger.info("Activating session %d: %s", session_id_idx, session_id)

        response = self.update_session("active", session_id=session_id)

        if response['status'] != 'activated':
            self.logger.error("Could not activate session.")

        self.sync_sessions()
        return response

    def close_session(self, session_id_idx=0, session_id=None):
        if session_id_idx != 0 and session_id is not None:
            self.logger.error("Invalid request: Both session ID index and session id provided! Aborting.")
            return

        if session_id is None:
            session_id = list(self.sessions)[session_id_idx]
            self.logger.info("Closing session %d: %s", session_id_idx, session_id)

        response = self.update_session("close", session_id=session_id)

        if not self._verify_key('status', response, 'closed'):
            self.logger.error("Could not close session.")
            return response

        self.logger.info("Closed session: %s", session_id)
        self._delete_data_streams(session_id)
        self.sync_sessions()

        return response

    def query_sessions(self, sync=True):
        params = {'cortexToken': self.cortex_token}
        response = self.send_authed_request(method="querySessions", params=params)

        if sync:
            self.sync_sessions(response, query=False)

        return response

    ## Helper Methods

    def sync_sessions(self, response=None, query=True):
        """Synchronise session related tracking vars with the server's."""
        if response is None:
            if query:
                response = self.query_sessions(sync=False)

        if type(response) == list:
            self.sessions.clear()

            for session in response:
                self.sessions[session['id']] = session

            self.logger.info("Session data updated!")
        else:
            self.logger.error("Could not query sessions!")

    ############################################################################
    # DATA SUBSCRIPTION
    ############################################################################

    def subscribe(self, streams, session_id_idx=0, session_id=None):
        if session_id_idx != 0 and session_id is not None:
            self.logger.error("Invalid request: Both session ID index and session id provided! Aborting.")
            return

        if session_id is None:
            session_id = list(self.sessions)[session_id_idx]
            self.logger.info("Subscribing to session %d: %s", session_id_idx, session_id)

        params = {'cortexToken': self.cortex_token,
                  'session': session_id,
                  'streams': streams}

        if not self.subscriber_spinning:
            self.spin_subscriber()
        else:
            self.logger.info("Subscriber already spinning. Skipping starting a new subscriber thread.")

        response = self.send_authed_request(method="subscribe", params=params)

        # Response sanity check
        if response.get('success') is None or response.get('failure') is None:
            if response.get('success') is None:
                self.logger.warning("Invalid subscription response. Aborting.")
                return response

        for stream in response.get('success'):
            try:
                if self.subscribed_streams.get(stream['sid']) is None:
                    self.subscribed_streams[stream['sid']] = {}
                else:
                    self.subscribed_streams[stream['sid']][stream['streamName']] = stream
            except Exception as e:
                self.logger.error(str(e))

        for stream in response.get('failure'):
            try:
                if self.subscribed_streams.get(stream['sid']) is None:
                    self.subscribed_streams[stream['sid']] = {}
                else:
                    self.subscribed_streams[stream['sid']][stream['streamName']] = "FAILED"
            except Exception as e:
                self.logger.error(str(e))

        return response

    def unsubscribe(self, streams, session_id_idx=0, session_id=None):
        if session_id_idx != 0 and session_id is not None:
            self.logger.error("Invalid request: Both session ID index and session id provided! Aborting.")
            return

        if session_id is None:
            session_id = list(self.sessions)[session_id_idx]
            self.logger.info("Unsubscribing from session %d: %s", session_id_idx, session_id)

        params = {'cortexToken': self.cortex_token,
                  'session': session_id,
                  'streams': streams}

        response = self.send_authed_request(method="unsubscribe", params=params)

        # Response sanity check
        if type(response) is not dict:
            if response.get('success') is None or response.get('failure') is None:
                self.logger.warning("Invalid unsubscription response. Aborting.")
                return response

        for stream in response.get('success'):
            try:
                self.subscribed_streams[session_id].pop(stream['streamName'])
            except Exception as e:
                self.logger.error(str(e))

        for stream in response.get('failure'):
            self.logger.error("Failed to unsubscribe: %s", str(stream))

        return response

    ## Helper Methods

    def receive_data(self, loop=None):
        if loop is None:
            loop = self._loop

        try:
            while self._loop.is_running():
                pass

            return loop.run_until_complete(self._recv_data())
        except Exception as e:
            self.logger.error(str(e))

    def spin_subscriber(self):
        """Spin up the subscriber thread."""
        # Try to kill the subscriber thread first before starting it
        try:
            self.stop_subscriber()
            self.subscriber_thread.join(10)
            self.logger.info("Pre-existing subscriber thread stopped!")
        except:
            pass

        self.stop_subscriber_flag = False
        self.subscriber_spinning = True
        self.subscriber_reading.set()

        self.subscriber_thread = Thread(target=self._subscriber_thread)
        self.subscriber_thread.start()

        # Disable server live checking as we will expect messages to drop
        self._websocket.ping_timeout = None

        self.logger.info("Subscriber thread started!")

    def stop_subscriber(self):
        """Kill subscriber thread."""
        self.stop_subscriber_flag = True

    def pause_subscriber(self):
        """Block subscriber thread, but don't kill it."""
        self.subscriber_reading.clear()

    def resume_subscriber(self):
        """Unblock subscriber thread."""
        self.subscriber_reading.set()

    def _subscriber_thread(self):
        """Subscriber thread main loop."""
        self.stop_subscriber_flag = False
        self.subscriber_spinning = True
        self.subscriber_messages_handled = 0
        # self._subscriber_loop = asyncio.new_event_loop()
        # asyncio.set_event_loop(self._subscriber_loop)

        while True:
            if self.interrupted:
                return
            try:
                if self.stop_subscriber_flag:
                    self.logger.info("Subscriber thread stopped")
                    self.subscriber_spinning = False
                    return

                if self.debug:
                    time.sleep(1)

                self.subscriber_reading.wait()

                try:
                    if not self._split_and_update_data_streams(self.receive_data()):
                        time.sleep(0.1)

                    self.subscriber_messages_handled += 1
                except Exception as e:
                    time.sleep(0.1)
                    self.logger.error("Subscriber thread: %s", str(e))
            except Exception as e:
                self.logger.error("Subscriber thread error!")
                self.logger.info(str(e))
                self.logger.info("Subscriber thread stopped")
                self.subscriber_spinning = False
                return

    def _create_data_streams(self, session_id):
        if self.data_streams.get(session_id) is None:
            self.data_streams[session_id] = {'eeg': deque(maxlen=self.data_deque_size),
                                             'mot': deque(maxlen=self.data_deque_size),
                                             'dev': deque(maxlen=self.data_deque_size),
                                             'pow': deque(maxlen=self.data_deque_size),
                                             'met': deque(maxlen=self.data_deque_size),
                                             'com': deque(maxlen=self.data_deque_size),
                                             'fac': deque(maxlen=self.data_deque_size),
                                             'sys': deque(maxlen=self.data_deque_size)}
        else:
            self.logger.warning("Data stream already exists! Could not create data stream for %s", str(session_id))

    def _delete_data_streams(self, session_id):
        try:
            self.data_streams.pop(session_id)
            self.logger.info("Session data streams for %s deleted!", str(session_id))
        except:
            self.logger.error("Could not delete session data stream for %s", str(session_id))

    def _split_and_update_data_streams(self, data_sample):
        # Each stream sample will be {'data': ..., 'time': ...}
        sample_integrity_flag = False

        if type(data_sample) is not dict:
            return False
        if data_sample.get("sid") is None:
            return False

        try:
            # Obtain data
            session_id = data_sample.pop("sid")
            time = data_sample.pop("time")
            stream_id, data = list(data_sample.items())[0]

            sample_integrity_flag = True

            # Push to data stream
            self.data_streams[session_id][stream_id].append({'data': data,
                                                             'time': time})

            return True
        except Exception as e:
            self.logger.error("Could not push data from data sample")
            self.logger.info(str(e))

            if not sample_integrity_flag:
                self.logger.warning("Invalid data sample received: %s", str(data_sample))
            else:
                self.logger.warning("Session id might not exist!")

    ############################################################################
    # RECORDS
    ############################################################################

    def create_record(self, title, session_id_idx=0, session_id=None, description=None, subject_name=None, tags=None):
        if session_id_idx != 0 and session_id is not None:
            self.logger.error("Invalid request: Both session ID index and session id provided! Aborting.")
            return

        if session_id is None:
            session_id = list(self.sessions)[session_id_idx]
            self.logger.info("Creating record for session %d: %s", session_id_idx, session_id)

        params = {'cortexToken': self.cortex_token,
                  'title': title,
                  'session': session_id}

        if description is not None:
            params['description'] = description

        if subject_name is not None:
            params['subjectName'] = subject_name

        if tags is not None:
            params['tags'] = tags

        return self.send_authed_request(method="createRecord", params=params)

    def stop_record(self, title, session_id_idx=0, session_id=None):
        if session_id_idx != 0 and session_id is not None:
            self.logger.error("Invalid request: Both session ID index and session id provided! Aborting.")
            return

        if session_id is None:
            session_id = list(self.sessions)[session_id_idx]
            self.logger.info("Stopping record for session %d: %s", session_id_idx, session_id)

        params = {'cortexToken': self.cortex_token,
                  'session': session_id}

        return self.send_authed_request(method="stopRecord", params=params)

    def update_record(self, record_id, description=None, tags=None):
        params = {'cortexToken': self.cortex_token,
                  'record': record_id}

        if description is not None:
            params['description'] = description

        if tags is not None:
            params['tags'] = tags

        self.logger.info("Updating record: %s", str(record_id))
        return self.send_authed_request(method="updateRecord", params=params)

    def delete_record(self, record_ids):
        if type(record_ids) is str:
            params = {'cortexToken': self.cortex_token,
                      'records': [record_ids]}
        else:
            params = {'cortexToken': self.cortex_token,
                      'records': record_ids}

        self.logger.info("Deleting records: %s", str(record_ids))
        return self.send_authed_request(method="deleteRecord", params=params)

    def export_record(self, record_ids, folder, format, stream_types, version=None):
        if type(record_ids) is str:
            record_ids = [record_ids]

        if type(stream_types) is str:
            stream_types = [stream_types]

        for stream_type in stream_types:
            assert any([stream_type == val for val in ["EEG", "MOTION", "PM", "BP"]]), "Valid stream types are: EEG, MOTION, PM, BP"

        format = format.upper()
        assert format == "EDF" or format == "CSV", "Valid formats are EDF or CSV only!"

        if format == "CSV":
            assert version == "V1" or version == "V2", "If format is CSV, please specify V1 or V2 for version!"

        params = {'cortexToken': self.cortex_token,
                  'records': record_ids,
                  'folder': folder,
                  'format': format,
                  'streamTypes': stream_types}

        if version is not None:
            params['version'] = version

        self.logger.info("Exporting records")
        return self.send_authed_request(method="exportRecord", params=params)

    def export_edf(self, record_ids, folder, stream_types):
        self.export_record(record_ids, folder, "EDF", stream_types)

    def export_csv_v1(self, record_ids, folder, stream_types):
        self.export_record(record_ids, folder, "CSV", stream_types, "V1")

    def export_csv_v2(self, record_ids, folder, stream_types):
        self.export_record(record_ids, folder, "CSV", stream_types, "V2")

    def query_records(self, query, order_by={'startDatetime': "DESC"}, limit=0, offset=0, include_markers=False):
        """
        Return list of records owned by current user.

        Query Formats:

        applicationId : string
        Set this parameter to filter the records by application.
        If you omit this parameter, then the method returns all the records of the user, from all applications.

        licenseId : string
        Set this parameter to filter the records by their license.

        keyword : string
        Set this parameter to filter the records by title, description, or subject.

        startDatetime : object
        An object with fields "from" and "to" to filter the records by their start date time.

        modifiedDatetime : object
        An object with fields "from" and "to" to filter the records by their modification date time.

        duration : object
        An object with fields "from" and "to" to filter the records by their duration.
        """

        params = {'cortexToken': self.cortex_token,
                  'query': query,
                  'orderBy': order_by,
                  'limit': limit,
                  'offset': offset,
                  'includeMarkers': include_markers}

        self.logger.info("Querying records...")
        return self.send_authed_request(method="queryRecords", params=params)

    def get_record_infos(self, record_ids):
        if type(record_ids) is str:
            params = {'cortexToken': self.cortex_token,
                      'records': [record_ids]}
        else:
            params = {'cortexToken': self.cortex_token,
                      'records': record_ids}

        self.logger.info("Retrieving records by ID...")
        return self.send_authed_request(method="getRecordInfos", params=params)

    ############################################################################
    # MARKERS
    ############################################################################

    def inject_marker(self, time, value, label, session_id_idx=0, session_id=None, port=None, extras=None):
        if session_id_idx != 0 and session_id is not None:
            self.logger.error("Invalid request: Both session ID index and session id provided! Aborting.")
            return

        if session_id is None:
            session_id = list(self.sessions)[session_id_idx]
            self.logger.info("Injecting marker for session %s: %s", session_id_idx, session_id)

        params = {'cortexToken': self.cortex_token,
                  'time': time,
                  'value': value,
                  'label': label,
                  'session': session_id}

        if port is not None:
            params['port'] = port

        if extras is not None:
            params['extras'] = extras

        return self.send_authed_request(method="injectMarker", params=params)

    def update_marker(self, marker_id, time, session_id_idx=0, session_id=None, extras=None):
        if session_id_idx != 0 and session_id is not None:
            self.logger.error("Invalid request: Both session ID index and session id provided! Aborting.")
            return

        if session_id is None:
            session_id = list(self.sessions)[session_id_idx]
            self.logger.info("Injecting marker for session %s: %s", session_id_idx, session_id)

        params = {'cortexToken': self.cortex_token,
                  'markerId': marker_id,
                  'time': time,
                  'session': session_id}

        if extras is not None:
            params['extras'] = extras

        return self.send_authed_request(method="updateMarker", params=params)

    ############################################################################
    # BCI
    ############################################################################

    def query_profiles(self):
        params = {'cortexToken': self.cortex_token}

        self.logger.info("Querying records...")
        return self.send_authed_request(method="queryProfile", params=params)

    def get_current_profile(self, headset_id_idx=0, headset_id=None):
        if len(self.headsets) == 0:
            self.sync_headsets()

        if headset_id_idx != 0 and headset_id is not None:
            self.logger.error("Invalid request: Both headset ID index and headset id provided! Aborting.")
            return

        if headset_id is None:
            headset_id = list(self.headsets)[headset_id_idx]
            self.logger.info("Retrieving current profile: %s", str(headset_id))

            params = {'cortexToken': self.cortex_token,
                      'headset': headset_id}

        return self.send_authed_request(method="getCurrentProfile", params=params)

    def setup_profile(self, status, profile, headset_id_idx=0, headset_id=None, new_profile_name=None):
        """General profile setup method."""
        if len(self.headsets) == 0:
            self.sync_headsets()

        if headset_id_idx != 0 and headset_id is not None:
            self.logger.error("Invalid request: Both headset ID index and headset id provided! Aborting.")
            return

        if headset_id is None:
            headset_id = list(self.headsets)[headset_id_idx]
            self.logger.info("Configuring profile %s with operation: %s", str(headset_id), str(status))

        status = status.lower()

        assert any([status == val for val in ["create",
                                              "load",
                                              "unload",
                                              "save",
                                              "rename",
                                              "delete"]]), "Valid statuses are: create, load, unload, save, rename, delete"

        params = {'cortexToken': self.cortex_token,
                  'status': status,
                  'profile': profile}

        if headset_id is not None:
            params['headset'] = headset_id
        if new_profile_name is not None:
            params['newProfileName'] = new_profile_name

        return self.send_authed_request(method="setupProfile", params=params)

    def create_profile(self, profile):
        self.setup_profile("create", profile)

    def load_profile(self, profile, headset_id_idx=0, headset_id=None):
        self.setup_profile("load", profile, headset_id_idx, headset_id)

    def unload_profile(self, profile, headset_id_idx=0, headset_id=None):
        self.setup_profile("unload", profile, headset_id_idx, headset_id)

    def save_profile(self, profile):
        self.setup_profile("save", profile)

    def rename_profile(self, profile, headset_id_idx=0, headset_id=None, new_profile_name=None):
        self.setup_profile("rename", profile, headset_id_idx, headset_id, new_profile_name)

    def delete_profile(self, profile):
        self.setup_profile("delete", profile)

    def load_guest_profile(self, headset_id_idx=0, headset_id=None):
        if len(self.headsets) == 0:
            self.sync_headsets()

        if headset_id_idx != 0 and headset_id is not None:
            self.logger.error("Invalid request: Both headset ID index and headset id provided! Aborting.")
            return

        if headset_id is None:
            headset_id = list(self.headsets)[headset_id_idx]
            self.logger.info("Loading guest profile for: %s", str(headset_id))

        params = {'cortexToken': self.cortex_token,
                  'headset': headset_id}

        return self.send_authed_request(method="loadGuestProfile", params=params)

    def get_detection_info(self, detection):
        assert detection == "mentalCommand" or detection == "facialExpression", "Valid detections: mentalCommand, facialExpression"
        return self.send_request(method="getDetectionInfo", params={'detection': detection})

    def get_mental_command_info(self):
        return self.send_request(method="getDetectionInfo", params={'detection': "mentalCommand"})

    def get_facial_expression_info(self):
        return self.send_request(method="getDetectionInfo", params={'detection': "facialExpression"})

    def training(self, detection, status, action, session_id_idx=0, session_id=None):
        """General training setup method."""
        if session_id_idx != 0 and session_id is not None:
            self.logger.error("Invalid request: Both session ID index and session id provided! Aborting.")
            return

        if session_id is None:
            session_id = list(self.sessions)[session_id_idx]
            self.logger.info("Injecting marker for session %s: %s", session_id_idx, session_id)

        assert any([detection == val for val in ["mentalCommand", "facialExpression"]]), "Valid detections are: mentalCommand or facialExpression"

        status = status.lower()
        assert any([status == val for val in ["start",
                                              "accept",
                                              "reject",
                                              "reset",
                                              "delete"]]), "Valid statuses are: start, accept, reject, reset, delete"

        params = {'cortexToken': self.cortex_token,
                  'session': session_id,
                  'detection': detection,
                  'status': status,
                  'action': action}

        return self.send_authed_request(method="training", params=params)

    def start_training(self, detection, action, session_id_idx=0, session_id=None):
        self.training(detection, "start", action, session_id_idx, session_id)

    def accept_training(self, detection, action, session_id_idx=0, session_id=None):
        self.training(detection, "accept", action, session_id_idx, session_id)

    def reject_training(self, detection, action, session_id_idx=0, session_id=None):
        self.training(detection, "reject", action, session_id_idx, session_id)

    def reset_training(self, detection, action, session_id_idx=0, session_id=None):
        self.training(detection, "reset", action, session_id_idx, session_id)

    def erase_training(self, detection, action, session_id_idx=0, session_id=None):
        self.training(detection, "erase", action, session_id_idx, session_id)

    ############################################################################
    # ADVANCED BCI
    ############################################################################

    def get_trained_signature_actions(self, detection, profile=None, session=None):
        assert any([detection == val for val in ["mentalCommand", "facialExpression"]]), "Valid detections are mentalCommand or facialExpression"

        params = {'cortexToken': self.cortex_token,
                  'detection': detection}

        if profile is None and session is None:
            self.logger.error("Invalid request: Either profile or session must be set!")
            return

        if profile is not None:
            params['profile'] = profile

        if session is not None:
            params['session'] = session

        return self.send_authed_request(method="getTrainedSignatureActions", params=params)

    def get_training_time(self, detection, session_id_idx=0, session_id=None):
        if session_id_idx != 0 and session_id is not None:
            self.logger.error("Invalid request: Both session ID index and session id provided! Aborting.")
            return

        if session_id is None:
            session_id = list(self.sessions)[session_id_idx]
            self.logger.info("Injecting marker for session %s: %s", session_id_idx, session_id)

        assert any([detection == val for val in ["mentalCommand", "facialExpression"]]), "Valid detections are mentalCommand or facialExpression"

        params = {'cortexToken': self.cortex_token,
                  'detection': detection,
                  'session': session_id}

        return self.send_authed_request(method="getTrainingTime", params=params)

    def facial_expression_signature_type(self, status, profile=None, session=None, signature=None):
        """General facial expression signature setup method."""
        assert any([status == val for val in ["get", "set"]]), "Valid statuses are: get or set"

        params = {'cortexToken': self.cortex_token,
                  'status': status}

        if profile is None and session is None:
            self.logger.error("Invalid request: Either profile or session must be set!")
            return

        if status == "set":
            assert signature is not None, "Signature must be set if status is 'set'. Use either universal or trained."

        if signature is not None:
            assert any([signature == val for val in ["universal", "trained"]]), "Valid signatures are: universal or trained"
            params['signature'] = signature

        if profile is not None:
            params['profile'] = profile

        if session is not None:
            params['session'] = session

        return self.send_authed_request(method="facialExpressionSignatureType", params=params)

    def get_facial_expression_signature_type(self, profile=None, session=None):
        self.facial_expression_signature_type("get", profile, session)

    def set_facial_expression_signature_type(self, profile=None, session=None, signature=None):
        self.facial_expression_signature_type("set", profile, session, signature)

    def facial_expression_threshold(self, status, action, profile=None, session=None, value=None):
        assert any([status == val for val in ["get", "set"]]), "Valid statuses are: get or set"
        assert any([action == val for val in ["neutral",
                                              "blink",
                                              "winkL",
                                              "winkR",
                                              "horiEye",
                                              "surprise",
                                              "frown",
                                              "smile",
                                              "clench",
                                              "laugh",
                                              "smirkLeft",
                                              "smirkRight"]]), "Valid actions are: neutral, blink, winkL, winkR, horiEye, surprise, frown, smile, clench, laugh, smirkLeft, smirkRight"

        if profile is None and session is None:
            self.logger.error("Invalid request: Either profile or session must be set!")
            return

        params = {'cortexToken': self.cortex_token,
                  'status': status,
                  'action': action}

        if status == "set":
            assert value is not None, "Value must be set if status is 'set'."
            assert value >= 0 and value <= 1000, "Value must be between 0 and 1000."

            params['value'] = value

        if profile is not None:
            params['profile'] = profile

        if session is not None:
            params['session'] = session

        return self.send_authed_request(method="facialExpressionThreshold", params=params)

    def get_facial_expression_threshold(self, action, profile=None, session=None):
        self.facial_expression_threshold("get", action, profile, session)

    def set_facial_expression_threshold(self, action, profile=None, session=None, value=None):
        self.facial_expression_threshold("set", action, profile, session, value)

    def mental_command_active_action(self, status, profile=None, session=None, actions=[]):
        assert any([status == val for val in ["get", "set"]]), "Valid statuses are: get or set"

        if profile is None and session is None:
            self.logger.error("Invalid request: Either profile or session must be set!")
            return

        params = {'cortexToken': self.cortex_token,
                  'status': status}

        if status == "set":
            assert type(actions) is list, "Pass in an list of actions!"

            if "neutral" in actions:
                assert len(actions) <= 5, "Only a maximum of 4 actions can be activated! (Not including neutral)"
            else:
                assert len(actions) <= 4, "Only a maximum of 4 actions can be activated! (Not including neutral)"

            for action in actions:
                assert any([action == val for val in ["neutral",
                                                      "push",
                                                      "pull",
                                                      "lift",
                                                      "drop",
                                                      "left",
                                                      "right",
                                                      "rotateLeft",
                                                      "rotateRight",
                                                      "rotateClockwise",
                                                      "rotateCounterClockwise",
                                                      "rotateForwards",
                                                      "rotateReverse",
                                                      "disappear"]]), "Valid actions are: neutral, push, pull, lift, drop, left, right, rotateLeft, rotateRight, rotateClockwise, rotateCounterClockwise, rotateForwards, rotateReverse, disappear"

            params['actions'] = actions

        if profile is not None:
            params['profile'] = profile

        if session is not None:
            params['session'] = session

        return self.send_authed_request(method="mentalCommandActiveAction", params=params)

    def get_mental_command_active_action(self, profile=None, session=None):
        self.mental_command_active_action("get", profile, session)

    def set_mental_command_active_action(self, profile=None, session=None, actions=[]):
        self.mental_command_active_action("set", profile, session, actions)

    def mental_command_brain_map(self, profile=None, session=None):
        if profile is None and session is None:
            self.logger.error("Invalid request: Either profile or session must be set!")
            return

        params = {'cortexToken': self.cortex_token}

        if profile is not None:
            params['profile'] = profile

        if session is not None:
            params['session'] = session

        return self.send_authed_request(method="mentalCommandBrainMap", params=params)

    def mental_command_get_skill_rating(self, profile=None, session=None, action=None):
        if profile is None and session is None:
            self.logger.error("Invalid request: Either profile or session must be set!")
            return

        assert any([action == val for val in [None,
                                              "neutral",
                                              "push",
                                              "pull",
                                              "lift",
                                              "drop",
                                              "left",
                                              "right",
                                              "rotateLeft",
                                              "rotateRight",
                                              "rotateClockwise",
                                              "rotateCounterClockwise",
                                              "rotateForwards",
                                              "rotateReverse",
                                              "disappear"]]), "Valid actions are: neutral, push, pull, lift, drop, left, right, rotateLeft, rotateRight, rotateClockwise, rotateCounterClockwise, rotateForwards, rotateReverse, disappear, or the NoneType"

        params = {'cortexToken': self.cortex_token}

        if profile is not None:
            params['profile'] = profile

        if session is not None:
            params['session'] = session

        if action is not None:
            params['action'] = action

        return self.send_authed_request(method="mentalCommandGetSkillRating", params=params)

    def mental_command_training_threshold(self, profile=None, session=None):
        if profile is None and session is None:
            self.logger.error("Invalid request: Either profile or session must be set!")
            return

        params = {'cortexToken': self.cortex_token}

        if profile is not None:
            params['profile'] = profile

        if session is not None:
            params['session'] = session

        return self.send_authed_request(method="mentalCommandTrainingThreshold", params=params)

    def mental_command_action_level(self, status, profile=None, session=None, level=None):
        """
        The action level is the confidence level of the action being probed.

        A higher level means a lower training threshold for good training
        performance.
        """
        assert any([status == val for val in ["get", "set"]]), "Valid statuses are: get or set"

        if profile is None and session is None:
            self.logger.error("Invalid request: Either profile or session must be set!")
            return

        params = {'cortexToken': self.cortex_token,
                  'status': status}

        if profile is not None:
            params['profile'] = profile

        if session is not None:
            params['session'] = session

        if status == "set":
            assert level is not None, "Level must be set if status is 'set'."
            assert level >= 1 and level <= 7, "Level must be between 1 and 7."

            params['level'] = level

        return self.send_authed_request(method="mentalCommandActionLevel", params=params)

    def get_mental_command_action_level(self, profile=None, session=None):
        self.mental_command_action_level("get", profile, session)

    def set_mental_command_action_level(self, profile=None, session=None, level=None):
        self.mental_command_action_level("set", profile, session, level)

    def mental_command_action_sensitivity(self, status, profile=None, session=None, values=[]):
        assert any([status == val for val in ["get", "set"]]), "Valid statuses are: get or set"

        if profile is None and session is None:
            self.logger.error("Invalid request: Either profile or session must be set!")
            return

        params = {'cortexToken': self.cortex_token,
                  'status': status}

        if profile is not None:
            params['profile'] = profile

        if session is not None:
            params['session'] = session

        if status == "set":
            assert type(values) is list, "Pass in an list of values!"
            assert len(values) <= 4, "Only a maximum of 4 values can be passed in! Put them in order of the actions set in mental_command_active_action()"

            for value in values:
                assert type(value) is int, "Value elements must be int!"
                assert value >= 1 and value <= 10, "Value elements must be between 1 and 7."

            params['values'] = values

        return self.send_authed_request(method="mentalCommandActionSensitivity", params=params)

    def get_mental_command_action_sensitivity(self, status, profile=None, session=None):
        self.mental_command_action_sensitivity("get", profile, session)

    def set_mental_command_action_sensitivity(self, status, profile=None, session=None, values=[]):
        self.mental_command_action_sensitivity("set", profile, session, values)
