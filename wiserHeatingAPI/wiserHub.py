"""
# Wiser API Facade

Angelosantagata@gmail.com


https://github.com/asantaga/wiserheatingapi


This API Facade allows you to communicate with your wiserhub.
This API is used by the homeassistant integration available at
https://github.com/asantaga/wiserHomeAssistantPlatform
"""

import logging
import requests
import json
import os
import re

_LOGGER = logging.getLogger(__name__)

"""
Wiser Data URLS
"""
WISERHUBURL = "http://{}/data/domain/"
WISERNETWORKURL =  "http://{}/data/network/"
WISERMODEURL = "http://{}/data/domain/System/RequestOverride"
WISERSETROOMTEMP = "http://{}//data/domain/Room/{}"
WISERROOM = "http://{}//data/domain/Room/{}"
WISERSCHEDULEURL = "http://{}/data/domain/Schedule/{}"
WISERSMARTPLUGURL = "http://{}/data/domain/SmartPlug/{}"
WISERSMARTPLUGSURL = "http://{}/data/domain/SmartPlug"

TEMP_MINIMUM = 5
TEMP_MAXIMUM = 30
TEMP_OFF = -20

TIMEOUT = 5

__VERSION__ = "1.0.3"

"""
Exception Handlers
"""


class Error(Exception):
    """Base class for exceptions in this module."""
    pass


class WiserNoDevicesFound(Error):
    pass


class WiserNotFound(Error):
    pass


class WiserNoRoomsFound(Error):
    pass


class WiserNoHotWaterFound(Error):
    pass


class WiserNoHeatingFound(Error):
    pass


class WiserRESTException(Error):
    pass


class WiserHubDataNull(Error):
    _LOGGER.info("WiserHub data null after refresh")
    pass

class WiserHubAuthenticationException(Error):
    pass

class WiserHubTimeoutException(Error):
    pass


class wiserHub:

    def __init__(self, hubIP, secret):
        _LOGGER.info(
            "WiserHub API Initialised : Version {}".format(__VERSION__))
        self.wiserHubData = None
        self.wiserNetworkData = None
        self.hubIP = hubIP
        self.hubSecret = secret
        self.headers = {'SECRET': self.hubSecret,
                        'Content-Type': 'application/json;charset=UTF-8'}
        # Dict holding Valve2Room mapping convinience variable
        self.device2roomMap = {}
        self.refreshData()  # Issue first refresh in init

    def __toWiserTemp(self, temp):
        """
        Converts from temperature to wiser hub format
        param temp: The temperature to convert
        return: Integer
        """
        temp = int(temp * 10)
        return temp

    def __fromWiserTemp(self, temp):
        """
        Conerts from wiser hub temperature format to decimal value
        param temp: The wiser temperature to convert
        return: Float
        """
        temp = round(temp / 10, 1)
        return temp

    def __checkTempRange(self, temp):
        """
        Validates temperatures are within the allowed range for the wiser hub
        param temp: The temperature to check
        return: Boolean
        """
        if temp != TEMP_OFF and (temp < TEMP_MINIMUM or temp > TEMP_MAXIMUM):
            return False
        else:
            return True

    def checkHubData(self):
        """
        Method checks the hub data object is populated, if it is not then it
        executes the refresh method, if the hubdata object is still null then
        it raises an error

        """
        if self.wiserHubData is None:
            self.refreshData()
        if self.wiserHubData is None:
            raise WiserHubDataNull(
                "Hub data null even after refresh, aborting request")
        # Otherwise continue

    def refreshData(self):
        """
        Forces a refresh of data from the wiser hub
        return: JSON Data
        """

        _LOGGER.info("Updating Wiser Hub Data")
        try:
            resp = requests.get(WISERHUBURL.format(
                self.hubIP), headers=self.headers, timeout=TIMEOUT)
                
            resp.raise_for_status()
            self.wiserHubData = resp.json()
            
            _LOGGER.debug(
                "Wiser Hub Data received {} ".format(self.wiserHubData))
            if self.getRooms() is not None:
                for room in self.getRooms():
                    roomStatId = room.get("RoomStatId")
                    if roomStatId is not None:
                        # RoomStat found add it to the list
                        self.device2roomMap[roomStatId] = {
                            "roomId": room.get("id"),
                            "roomName": room.get("Name")}
                    smartValves = room.get("SmartValveIds")
                    if smartValves is not None:
                        for valveId in smartValves:
                            self.device2roomMap[valveId] = {
                                "roomId": room.get("id"),
                                "roomName": room.get("Name")}
                    # Show warning if room contains no devices.
                    if roomStatId is None and smartValves is None:
                        # No devices in room
                        _LOGGER.warning(
                            "Room {} doesn't contain any smart valves or thermostats.".format(
                                room.get("Name")))
                _LOGGER.debug(" valve2roomMap{} ".format(self.device2roomMap))
            else:
                _LOGGER.warning("Wiser found no rooms")

            # The Wiser Heat Hub can return invalid JSON, so remove all non-printable characters before trying to parse JSON
            responseContent = requests.get(WISERNETWORKURL.format(self.hubIP), headers=self.headers, timeout=TIMEOUT).content
            responseContent = re.sub(rb'[^\x20-\x7F]+', b'', responseContent)
            self.WiserNetworkData = json.loads(responseContent)

        except requests.Timeout:
            _LOGGER.debug(
                "Connection timed out trying to update from Wiser Hub")
            raise WiserHubTimeoutException("The connection timed out.")
        except requests.HTTPError:
            if self.wiserHubData.status_code == 401:
                raise WiserHubAuthenticationException("Authentication error.  Check secret key.")
            elif self.wiserHubData.status_code == 404:
                raise WiserRESTException("Not Found.")
            else:
                raise WiserRESTException("Unknown Error.")
        except requests.ConnectionError:
            _LOGGER.debug("Connection error trying to update from Wiser Hub")
        return self.wiserHubData

    def getHubData(self):
        """
        Retrieves the full JSON payload ,
        for functions where I haven't provided a API yet

        returns : JSON Data
        """
        self.checkHubData()
        return self.wiserHubData

    def getWiserHubName(self):
        return self.wiserNetworkData.get("Station").get("MdnsHostname")
        
    def getMACAddress(self):
        return self.wiserNetworkData.get("Station").get("MacAddress")
        
    def getRooms(self):
        """
        Gets Room Data as JSON Payload
        """
        self.checkHubData()
        return self.wiserHubData.get("Room")

    def getRoom(self, roomId):
        """
        Convinience to get data on a single room

        param roomId: The roomID
        return:
        """
        self.checkHubData()
        if self.wiserHubData.get("Room") is None:
            _LOGGER.warning("getRoom called but no rooms found")
            raise WiserNoRoomsFound("No rooms found in Wiser payload")
        for room in (self.wiserHubData.get("Room")):
            if room.get("id") == roomId:
                return room
        raise WiserNotFound("Room {} not found".format(roomId))

    def getSystem(self):
        """
        Convinience function to get system information

        return: JSON with system data
        """
        self.checkHubData()
        return self.wiserHubData.get("System")

    def getHotwater(self):
        """
        Convinience function to get hotwater data

        return: JSON with hotwater data

        """
        self.checkHubData()
        return self.wiserHubData.get("HotWater")

    def getHeatingChannels(self):
        """
        Convinience function to get heating channel data

        return: JSON data
        """
        self.checkHubData()
        return self.wiserHubData.get("HeatingChannel")

    def getDevices(self):
        """
        Convinience function to get devices data

        return: JSON data
        """
        self.checkHubData()

        return self.wiserHubData.get("Device")

    def getDevice(self, deviceId):
        """
        Get single devices data

        param deviceId:
        return: Device JSON Data
        """
        self.checkHubData()

        if self.wiserHubData.get("Device") is None:
            _LOGGER.warning("getRoom called but no rooms found")
            raise WiserNoRoomsFound("getRoom called but no rooms found")
        for device in (self.wiserHubData.get("Device")):
            if device.get("id") == deviceId:
                return device
        raise WiserNotFound("Device {} not found ".format(deviceId))

    def getDeviceRoom(self, deviceId):
        """
        Convinience function to return the name of a room which is associated
        with a device (roomstat or trf)
        param deviceId:
        return: Name of Room associated with a device ID
        """
        self.checkHubData()
        _LOGGER.debug(" getDeviceRoom called, valve2roomMap is {} ".format(
            self.device2roomMap))
        if not self.device2roomMap:
            self.refreshData()
        # This will return None if no device found, thats ok
        return self.device2roomMap[deviceId]

    def getHeatingRelayStatus(self):
        """
        Returns heating relay status
        return:  On or Off
        """
        # self.checkHubData()
        heatingRelayStatus = "Off"
        # There could be multiple heating channels, 
        heatingChannels = self.getHeatingChannels()
        for heatingChannel in heatingChannels:
            if heatingChannel.get("HeatingRelayState") == "On":
                heatingRelayStatus = "On"
        return heatingRelayStatus

    def getHotwaterRelayStatus(self):
        """
         Returns hotwater relay status
        return:  On or Off

        """
        self.checkHubData()
        """
        If there is no hotwater object then return false
        """
        if len(self.wiserHubData.get("HotWater")) < 1:
            return False

        return self.wiserHubData.get("HotWater")[0].get("WaterHeatingState")

    def setHotwaterMode(self, mode):
        """
          Switch Hot Water on or off manually, or reset to 'Auto' (schedule).
          'mode' can be "on", "off" or "auto".
        """

        # Wiser requires a temperature when patching the Hot Water state,
        # reflecting 'on' or 'off'
        DHWOnTemp = 1100
        DHWOffTemp = -200

        modeMapping = {
            'on': {
                "RequestOverride": {"Type": "Manual", "SetPoint": DHWOnTemp}},
            'off': {
                "RequestOverride": {"Type": "Manual", "SetPoint": DHWOffTemp}},
            'auto': {"RequestOverride": {"Type": "None", "Mode": "Auto"}},
        }

        _mode = mode.lower()
        if _mode not in ['on', 'off', 'auto']:
            raise ValueError(
                "Hot Water can be either 'on', 'off' or 'auto' - not '%s'" % _mode)

        # Obtain our DHW control ID
        if self.wiserHubData is None:
            self.refreshData()
        DHWId = self.wiserHubData.get("HotWater")[0].get("id")

        _url = WISERHUBURL.format(self.hubIP) + "/HotWater/{}/".format(DHWId)
        _LOGGER.debug("Sending Patch Data: {}, to URL [{}]".format(
            modeMapping.get(_mode), _url))
        response = requests.patch(url=_url, headers=self.headers,
                                       json=modeMapping.get(_mode))
        if response.status_code != 200:
            _LOGGER.debug(
                "Set DHW Response code = {}".format(response.status_code))
            raise WiserRESTException(
                "Error setting hot water mode to {}, error {} {}".
                    format(_mode, response.status_code, response.text))

        return True

    def setSystemSwitch(self, switch, mode=False):
        """
        Sets a system switch. For details of which switches to set look at the System section of the payload from the wiserhub
        :param switch: Name of Switch
        :param mode: Value of mode
        :return:
        """
        patchData = {switch: mode}
        url = WISERHUBURL + "System"

        _LOGGER.debug("patchdata {} ".format(patchData))
        response = requests.patch(url=url.format(self.hubIP),
                                       headers=self.headers,
                                       json=patchData, timeout=TIMEOUT)
        if response.status_code != 200:
            _LOGGER.debug("Set {} Response code = {}".format(switch,
                                                             response.status_code))
            raise WiserRESTException(
                "Error setting {} , error {} {}".format(switch,
                                                        response.status_code,
                                                        response.text))

    def getRoomStatData(self, deviceId):
        """
        Gets Room Thermostats Data

        param deviceId:
        return:
        """
        self.checkHubData()

        if self.wiserHubData['RoomStat'] is None:
            _LOGGER.warning("getRoomStatData called but no RoomStats found")
            raise WiserNotFound("deviceID {} not found ".format(deviceId))

        for roomStat in self.wiserHubData['RoomStat']:
            if roomStat.get("id") == deviceId:
                return roomStat
        """
        If we get here then the deviceId was not found
        """
        raise WiserNotFound(
            "getRoomStatData for deviceID {} not found due".format(deviceId))

    def getRoomSchedule(self, roomId):
        """
        Gets Room Schedule Data
        
        param roomId:
        return: json data
        """
        self.checkHubData()

        if self.getRoom(roomId) is None:
            raise WiserNotFound(
                "getRoomSchedule for room {} not found ".format(roomId))

        scheduleId = self.getRoom(roomId).get("ScheduleId")
        if scheduleId is not None:
            for schedule in (self.wiserHubData.get("Schedule")):
                if schedule.get("id") == scheduleId:
                    return schedule
            raise WiserNotFound(
                "getRoomSchedule for room {} not found ".format(roomId))
        else:
            raise WiserNotFound(
                "getRoomSchedule for room {} not found ".format(roomId))

    def setRoomSchedule(self, roomId, scheduleData: dict):
        """
        Sets Room Schedule

        param roomId:
        param scheduleData: json data for schedule
        return:
        """
        scheduleId = self.getRoom(roomId).get("ScheduleId")

        if scheduleId is not None:
            patchData = scheduleData
            response = requests.patch(
                url=WISERSCHEDULEURL.format(self.hubIP, scheduleId),
                headers=self.headers, json=patchData, timeout=TIMEOUT)

            if response.status_code != 200:
                _LOGGER.debug("Set Schedule Response code = {}".format(
                    response.status_code))
                raise WiserRESTException(
                    "Error setting schedule for room {} , error {} {}".format(
                        roomId, response.status_code, response.text))
        else:
            raise WiserNotFound("No schedule found that matches roomId")

    def setRoomScheduleFromFile(self, roomId, scheduleFile: str):
        """
        Sets Room Schedule

        param roomId:
        param scheduleData: json data for schedule
        return:
        """
        scheduleId = self.getRoom(roomId).get("ScheduleId")


        if scheduleId is not None:
            if os.path.exists(scheduleFile):
                try:
                    with open(scheduleFile, 'r') as f:
                        scheduleData = json.load(f)
                except:
                    raise Exception(
                        "Error reading file {}".format(scheduleFile))

                patchData = scheduleData
                response = requests.patch(
                    url=WISERSCHEDULEURL.format(self.hubIP, scheduleId),
                    headers=self.headers, json=patchData, timeout=TIMEOUT)

                if response.status_code != 200:
                    _LOGGER.debug("Set Schedule Response code = {}".format(
                        response.status_code))
                    raise WiserRESTException(
                        "Error setting schedule for room {} , error {} {}".format(
                            roomId, response.status_code,
                            response.text))
            else:
                raise FileNotFoundError("Schedule file, {}, not found.".format(
                    os.path.abspath(scheduleFile)))
        else:
            raise WiserNotFound("No schedule found that matches roomId")

    def copyRoomSchedule(self, fromRoomId, toRoomId):
        """
        Copies Room Schedule from one room to another

        param fromRoomId:
        param toRoomId:
        return: boolean
        """
        scheduleData = self.getRoomSchedule(fromRoomId)

        print(json.dumps(scheduleData))

        print("TYPE:{}".format(type(scheduleData)))

        if scheduleData is not None:
            self.setRoomSchedule(toRoomId, scheduleData)
        else:
            raise WiserNotFound(
                "Error copying schedule.  One of the room Ids is not valid")

    def setHomeAwayMode(self, mode, temperature=10):
        """
        Sets default Home or Away mode, optionally allows you to set a temperature for away mode

        param mode: HOME   | AWAY

        param temperature: Temperature between 5-30C or -20 for OFF

        return:
        """
        _LOGGER.info(
            "Setting Home/Away mode to : {} {} C".format(mode, temperature))


        if mode not in ['HOME', 'AWAY']:
            raise ValueError("setAwayHome can only be HOME or AWAY")

        if mode == "AWAY":
            if temperature is None:
                raise ValueError(
                    "setAwayHome set to AWAY but not temperature set")
            if not (self.__checkTempRange(temperature)):
                raise ValueError(
                    "setAwayHome temperature can only be between {} and {} or {}(Off)".format(
                        TEMP_MINIMUM, TEMP_MAXIMUM, TEMP_OFF))
        _LOGGER.info("Setting Home/Away : {}".format(mode))

        if mode == "AWAY":
            patchData = {"type": 2,
                              "setPoint": self.__toWiserTemp(temperature)}
        else:
            patchData = {"type": 0, "setPoint": 0}
        _LOGGER.debug("patchdata {} ".format(patchData))
        response = requests.patch(url=WISERMODEURL.format(self.hubIP),
                                       headers=self.headers,
                                       json=patchData, timeout=TIMEOUT)
        if response.status_code != 200:
            _LOGGER.debug("Set Home/Away Response code = {}".format(
                response.status_code))
            raise ValueError("Error setting Home/Away , error {} {}".format(
                response.status_code, response.text))

    def setRoomTemperature(self, roomId, temperature):
        """
        Sets the room temperature
        param roomId:  The Room ID
        param temperature:  The temperature in celcius from 5 to 30, -20 for Off
        """
        _LOGGER.info(
            "Set Room {} Temperature to = {} ".format(roomId, temperature))
        if not (self.__checkTempRange(temperature)):
            raise ValueError(
                "SetRoomTemperature : value of temperature must be between {} and {} OR {} (off)".format(
                    TEMP_MINIMUM, TEMP_MAXIMUM, TEMP_OFF))
        patchData = {"RequestOverride": {"Type": "Manual",
                                         "SetPoint": self.__toWiserTemp(
                                             temperature)}}
        response = requests.patch(WISERSETROOMTEMP.format(
            self.hubIP, roomId), headers=self.headers, json=patchData,
            timeout=TIMEOUT)
        if response.status_code != 200:
            _LOGGER.error(
                "Set Room {} Temperature to = {} resulted in {}".format(roomId,
                                                                        temperature,
                                                                        response.status_code))
            raise WiserRESTException(
                "Error setting temperature, error {} ".format(
                    response.text))
        _LOGGER.debug(
            "Set room Temp, error {} ({})".format(response.status_code,
                                                  response.text))

    # Set Room Mode (Manual, Boost,Off or Auto )
    # If set to off then the trv goes to manual and temperature of -200
    #
    def setRoomMode(self, roomId, mode, boost_temp=20, boost_temp_time=30):
        """
        Set the Room Mode, this can be Auto, Manual, off or Boost. When you set the mode back to Auto it will automatically take the scheduled temperature

        param roomId: RoomId

        param mode:  Mode (auto, manual off, or boost)

        param boost_temp:  If boosting enter the temperature here in C, can be between 5-30

        param boost_temp_time:  How long to boost for in minutes

        """
        # TODO
        _LOGGER.debug("Set Mode {} for a room {} ".format(mode, roomId))
        if mode.lower() == "auto":
            # Do Auto
            patchData = {"Mode": "Auto"}
        elif mode.lower() == "boost":
            if boost_temp < TEMP_MINIMUM or boost_temp > TEMP_MAXIMUM:
                raise ValueError(
                    "Boost temperature is set to {}. Boost temperature can only be between {} and {}.".format(
                        boost_temp, TEMP_MINIMUM, TEMP_MAXIMUM))
            _LOGGER.debug(
                "Setting room {} to boost mode with temp of {} for {} mins".format(
                    roomId, boost_temp, boost_temp_time))
            patchData = {"RequestOverride": {"Type": "Manual",
                                             "DurationMinutes": boost_temp_time,
                                             "SetPoint": self.__toWiserTemp(
                                                 boost_temp),
                                             "Originator": "App"}}
        elif mode.lower() == "manual":
            # When setting to manual , set the temp to the current scheduled temp 
            setTemp = self.__fromWiserTemp(
                self.getRoom(roomId).get("ScheduledSetPoint"))
            # If current scheduled temp is less than 5C then set to min temp
            setTemp = setTemp if setTemp >= TEMP_MINIMUM else TEMP_MINIMUM
            patchData = {"Mode": "Manual",
                         "RequestOverride": {"Type": "Manual",
                                             "SetPoint": self.__toWiserTemp(
                                                 setTemp)}}
        # Implement trv off as per https://github.com/asantaga/wiserheatingapi/issues/3
        elif mode.lower() == "off":
            patchData = {"Mode": "Manual",
                         "RequestOverride": {"Type": "Manual",
                                             "SetPoint": self.__toWiserTemp(
                                                 TEMP_OFF)}}
        else:
            raise ValueError(
                "Error setting setting room mode, received  {} but should be auto,boost,off or manual ".format(
                    mode))

        # if not a boost operation cancel any current boost
        if mode.lower() != "boost":
            cancelBoostPostData = {
                "RequestOverride": {"Type": "None", "DurationMinutes": 0,
                                    "SetPoint": 0, "Originator": "App"}}

            response = requests.patch(
                WISERROOM.format(self.hubIP, roomId), headers=self.headers,
                json=cancelBoostPostData, timeout=TIMEOUT)
            if response.status_code != 200:
                _LOGGER.error("Cancelling boost resulted in {}".format(
                    response.status_code))
                raise WiserRESTException(
                    "Error cancelling boost {} ".format(mode))

        # Set new mode
        response = requests.patch(WISERROOM.format(
            self.hubIP, roomId), headers=self.headers, json=patchData,
            timeout=TIMEOUT)
        if response.status_code != 200:
            _LOGGER.error(
                "Set Room {} to Mode {} resulted in {}".format(roomId, mode,
                                                               response.status_code))
            raise WiserRESTException(
                "Error setting mode to {}, error {} ".format(mode,
                                                             response.text))
        _LOGGER.debug(
            "Set room mode, error {} ({})".format(response.status_code,
                                                  response.text))

    def getSmartPlugs(self):
        self.checkHubData()
        return self.getHubData().get("SmartPlug")

    def getSmartPlug(self,smartPlugId):
        self.checkHubData()
        if self.getHubData().get("SmartPlug") is not None:
            for plug in self.getHubData().get("SmartPlug"):
                if plug.get("id") == smartPlugId:
                    return plug
        # If we get here then the plug was not found
        raise WiserNotFound("Unable to find smartPlug {}".format(smartPlugId))

    def getSmartPlugState(self, smartPlugId):
        self.checkHubData()
        if self.getHubData().get("SmartPlug") is not None:
            for plug in self.getHubData().get("SmartPlug"):
                if plug.get("id") == smartPlugId:
                    return plug.get("OutputState")
        # If we get here then the plug was not found
        raise WiserNotFound("Unable to find smartPlug {}".format(smartPlugId))

    def setSmartPlugState(self, smartPlugId, smartPlugState):

        if smartPlugState.title() not in ["On", "Off"]:
            _LOGGER.error("SmartPlug State must be either On or Off")
            raise ValueError("SmartPlug State must be either On or Off")

        url = WISERSMARTPLUGURL.format(self.hubIP, smartPlugId)
        patchData = {"RequestOutput": smartPlugState.title()}

        _LOGGER.debug(
            "Setting smartplug status patchdata {} ".format(patchData))
        response = requests.patch(url=url.format(self.hubIP),
                                  headers=self.headers,
                                  json=patchData,
                                  timeout=TIMEOUT)
        if response.status_code != 200:
            if response.status_code == 404:
                _LOGGER.debug("Set smart plug not found error ")
                raise WiserNotFound(
                    "Set smart plug {} not found error".format(smartPlugId))
            else:
                _LOGGER.debug(
                    "Set smart plug error {} Response code = {}".format(
                        response.text, response.status_code))
                raise WiserRESTException(
                    "Error setting smartplug mode, msg {} , error {}".format(
                        response.status_code,
                        response.text))

    def getSmartPlugMode(self, smartPlugId):
        self.checkHubData()
        if self.getHubData().get("SmartPlug") is not None:
            for plug in self.getHubData().get("SmartPlug"):
                if plug.get("id") == smartPlugId:
                    return plug.get("Mode")
        # If we get here then the plug was not found
        raise WiserNotFound("Unable to find smartPlug {}".format(smartPlugId))

    def setSmartPlugMode(self, smartPlugId, smartPlugMode):

        if smartPlugMode.title() not in ["Auto", "Manual"]:
            _LOGGER.error("SmartPlug Mode must be either Auto or Manual")
            raise ValueError("SmartPlug Mode must be either Auto or Manual")

        url = WISERSMARTPLUGURL.format(self.hubIP, smartPlugId)
        patchData = {"Mode": smartPlugMode.title()}

        _LOGGER.debug(
            "Setting smartplug status patchdata {} ".format(patchData))
        response = requests.patch(url=url.format(self.hubIP),
                                  headers=self.headers,
                                  json=patchData,
                                  timeout=TIMEOUT)
        if response.status_code != 200:
            if response.status_code == 404:
                _LOGGER.debug("Set smart plug not found error ")
                raise WiserNotFound(
                    "Set smart plug {} not found error".format(smartPlugId))
            else:
                _LOGGER.debug(
                    "Set smart plug error {} Response code = {}".format(
                        response.text, response.status_code))
                raise WiserRESTException(
                    "Error setting smartplug mode, msg {} , error {}".format(
                        response.status_code,
                        response.text))


