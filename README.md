# Emotiv Cortex2 Python Client

Author: methylDragon

---

![Image result for emotiv epoc](./assets/Epoc-product-image.png)

![Image result for emotiv logo](./assets/Emotiv_logo.svg.png)

Image sources: [Emotiv](emotiv.com)



## Introduction

Unofficial Python client for the Emotiv EEG Cortex 2 API.

Features the entire JSON-RPC API communicated via asynchronous websockets for speed.

The Cortex 2 app is used to host a websocket web server gateway interface that takes JSON requests and returns JSON data.

This Python client is designed to be a wrapper client for said API. It streams multi-session sensor data using a separate asynchronous thread!

API Reference: https://emotiv.gitbook.io/cortex-api/



## Support my efforts!

 [![Yeah! Buy the DRAGON a COFFEE!](./assets/COFFEE%20BUTTON%20%E3%83%BE(%C2%B0%E2%88%87%C2%B0%5E).png)](https://www.buymeacoffee.com/methylDragon)

[Or leave a tip! ヾ(°∇°*)](https://www.paypal.me/methylDragon)



## Requirements

- Python 3.6 or above



## Installation

```shell
pip install cortex2
```



## Example Usage

Remember to set up your client ID and secret by [registering](https://www.emotiv.com/developer/)

Also ensure you've started the EmotivApp, since it hosts the websocket server! (You'll probably have to use Windows or Mac.)

If the client fails to connect, you might have to restart the script using the client.

```python
from cortex2 import EmotivCortex2Client

url = "wss://localhost:6868"

# Remember to start the Emotiv App before you start!
# Start client with authentication
client = EmotivCortex2Client(url,
                             client_id='CLIENT_ID',
                             client_secret="CLIENT_SECRET",
                             check_response=True,
                             authenticate=True,
                             debug=False)

# Test API connection by using the request access method
client.request_access()

# Explicit call to Authenticate (approve and get Cortex Token)
client.authenticate()

# Connect to headset, connect to the first one found, and start a session for it
client.query_headsets()
client.connect_headset(0)
client.create_session(0)

# Subscribe to the motion and mental data streams
# Spins up a separate subscription thread
client.subscribe(streams=["mot", "met"])

# Test message handling speed
a = client.subscriber_messages_handled
time.sleep(5)
b = client.subscriber_messages_handled
print((b - a) / 5)

# Grab a single instance of data
print(client.receive_data())

# Continously grab data, while making requests periodically
while True:
    counter += 1
    # time.sleep(0.1)

    if counter % 5000 == 0:
        print(client.request_access())
        
    # Try stopping the subscriber thread
    if counter == 50000:
        client.stop_subscriber()
        break
        
    try:
        # Check the latest data point from the motion stream, from the first session
        print(list(client.data_streams.values())[0]['mot'][0])
    except:
        pass
```

**You can also connect by explicitly stating IDs!**

```python
client.connect_headset(headset_id="EPOCPLUS-3B9AXXXX")
client.create_session(headset_id="EPOCPLUS-3B9AXXXX")
```

**You can do a lot more! The entire API is covered, and everything generally works the same way.**



## Additional Notable Features

- The websockets API is wrapped with helper functions to do request ID checking, asynchronous message handling, and some basic data sanitisation
- Threads are used to try to allow for subscription to **multiple** sessions and **multiple** headsets
  - The threads have a helper function that automatically splits the data streams so you may work on the streams independently as opposed to all lumped together as one object
- Automatic syncing helper methods for detecting existing sessions and headsets will fire off when the relevant methods are called. (Eg. when trying to update, connect, or disconnect headsets, the client will automatically query and update the dictionary of seen headsets.)



## Notable Class Attributes

| Name                        | Type              | Description                                                  | Example                                               |
| --------------------------- | ----------------- | ------------------------------------------------------------ | ----------------------------------------------------- |
| debug                       | bool              | Debug flag. Slows down data subscription rate if set.        |                                                       |
| client_id                   | str               | Client ID                                                    |                                                       |
| client_secret               | str               | Client Secret                                                |                                                       |
| cortex_token                | str               | Cortex Token                                                 |                                                       |
| approved                    | bool              | True if access is granted                                    |                                                       |
| authorized                  | bool              | True if cortex token is issued                               |                                                       |
| headsets                    | OrderedDict()     | OrderedDict of headset object dicts seen                     |                                                       |
| connected_headsets          | OrderedDict()     | OrderedDict of connected headset object dicts                |                                                       |
| sessions                    | OrderedDict()     | OrderedDict of seen session object dicts                     |                                                       |
| data_deque_size             | int               | Maximum size of each subscriber data buffer                  |                                                       |
| data_streams                | dict              | Sensor data streams keyed by session                         | {session_id: {data_stream_deques_types: [data]}, ...} |
| subscribed_streams          | dict              | Data stream names and descriptions that are subscribed, keyed by session | {session_id: {stream_names: info}, ...}               |
| subscriber_spinning         | bool              | Tracks whether the subscriber thread is running              |                                                       |
| subscriber_messages_handled | int               | Counts how many subscriber messages have been handled        |                                                       |
| subscriber_reading          | threading.Event() | Event flag to pause the subscriber without killing it        |                                                       |



## Class Methods

### Class Helpers

- `send_authed_request(method=None, params={}, request=None)`
- `send_request(method=None, params={}, request=None)`
- `set_client_id(client_id)`
- `set_client_secret(client_secret)`
- `_verify_key(key, response, field=None`)
- `_exit_handler(\_signo, _stack_frame)`

---

### Connecting to Cortex API

- `get_cortex_info()`

---

### Authentication

- `get_user_login()`
- `request_access()`
- `has_access_right()`
- `authorize()`
- `generate_new_token()`
- `get_user_information()`
- `get_license_info()`



- **Helpers**
  - `authenticate()`

---

### Headsets

- `query_headsets(id=None, sync=True)`
- `control_device(command, headset_id=None, mappings=None)`
- `refresh_headsets()`
- `connect_headset(headset_id_idx=0, headset_id=None, mappings=None)`
- `disconnect_headset(headset_id)`
- `update_headset(settings, headset_id_idx=0, headset_id=None)`
- `maximise_headset(headset_id_idx=0, headset_id=None)`
- `maximise_headset_no_motion(headset_id_idx=0, headset_id=None)`



- **Helpers**
  - `sync_headsets(response=None, query=True)`
  - `_get_headset_type(headset_id)`

---

### Sessions

- `create_session(headset_id_idx=0, headset_id=None)`
- `create_activated_session(headset_id_idx=0, headset_id=None)`
- `update_session(status, session_id_idx=0, session_id=None)`
- `activate_session(session_id_idx=0, session_id=None)`
- `close_session(session_id_idx=0, session_id=None)`
- `query_sessions(sync=True)`



- **Helpers**
  - `sync_sessions(response=None, query=True)`

---

### Data Subscription

- `subscribe(streams, session_id_idx=0, session_id=None)`
- `unsubscribe(streams, session_id_idx=0, session_id=None)`



- #### **Helpers**
  
  - `receive_data()`
  - `spin_subscriber()`
  - `stop_subscriber()`
  - `pause_subscriber()`
  - `resume_subscriber()`
  - `_subscriber_thread()`
  - `_create_data_streams(session_id)`
  - `_delete_data_streams(session_id)`
  - `_split_and_update_data_streams(data_sample)`

---

### Records

- `create_record(title, session_id_idx=0, session_id=None, description=None, subject_name=None, tags=None)`
- `stop_record(title, session_id_idx=0, session_id=None)`
- `update_record(record_id, description=None, tags=None)`
- `delete_record(record_ids)`
- `export_record(record_ids, folder, format, stream_types, version=None)`
- `export_edf(record_ids, folder, stream_types)`
- `export_csv_v1(record_ids, folder, stream_types)`
- `export_csv_v2(record_ids, folder, stream_types)`
- `query_records(query, order_by={'startDatetime': "DESC"}, limit=0, offset=0, include_markers=False)`
- `get_record_infos(record_ids)`

---

### Markers

- `inject_marker(time, value, label, session_id_idx=0, session_id=None, port=None, extras=None)`
- `update_marker(marker_id, time, session_id_idx=0, session_id=None, extras=None)`

---

### BCI

- `query_profiles()`
- `get_current_profile(headset_id_idx=0, headset_id=None)`
- `setup_profile(status, profile, headset_id_idx=0, headset_id=None, new_profile_name=None)`
- `create_profile(profile)`
- `load_profile(profile, headset_id_idx=0, headset_id=None)`
- `unload_profile(profile, headset_id_idx=0, headset_id=None)`
- `save_profile(profile)`
- `rename_profile(profile, headset_id_idx=0, headset_id=None, new_profile_name=None)`
- `delete_profile(profile)`
- `load_guest_profile(headset_id_idx=0, headset_id=None)`
- `get_detection_info(detection)`
- `get_mental_command_info()`
- `get_facial_expression_info()`
- `training(detection, status, action, session_id_idx=0, session_id=None)`
- `start_training(detection, action, session_id_idx=0, session_id=None)`
- `accept_training(detection, action, session_id_idx=0, session_id=None)`
- `reject_training(detection, action, session_id_idx=0, session_id=None)`
- `reset_training(detection, action, session_id_idx=0, session_id=None)`
- `erase_training(detection, action, session_id_idx=0, session_id=None)`



---

### Advanced BCI

- `get_trained_signature_actions(detection, profile=None, session=None)`
- `get_training_time(detection, session_id_idx=0, session_id=None)`
- `facial_expression_signature_type(status, profile=None, session=None, signature=None)`
- `get_facial_expression_signature_type(profile=None, session=None)`
- `set_facial_expression_signature_type(profile=None, session=None, signature=None)`
- `facial_expression_threshold(status, action, profile=None, session=None, value=None)`
- `get_facial_expression_threshold(action, profile=None, session=None)`
- `set_facial_expression_threshold(action, profile=None, session=None, value=None)`
- `mental_command_active_action(status, profile=None, session=None, actions=[])`
- `get_mental_command_active_action(profile=None, session=None)`
- `set_mental_command_active_action(profile=None, session=None, actions=[])`
- `mental_command_brain_map(profile=None, session=None)`
- `mental_command_get_skill_rating(profile=None, session=None, action=None)`
- `mental_command_training_threshold(profile=None, session=None)`
- `mental_command_action_level(status, profile=None, session=None, level=None)`
- `get_mental_command_action_level(profile=None, session=None)`
- `set_mental_command_action_level(profile=None, session=None, level=None)`
- `mental_command_action_sensitivity(status, profile=None, session=None, values=[])`
- `get_mental_command_action_sensitivity(status, profile=None, session=None)`
- `set_mental_command_action_sensitivity(status, profile=None, session=None, values=[])`