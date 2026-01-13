# ableton_mcp_server.py
from mcp.server.fastmcp import FastMCP, Context
import socket
import json
import logging
from dataclasses import dataclass
from contextlib import asynccontextmanager
from typing import AsyncIterator, Dict, Any, List, Union
from .m4l_utils import set_parameter_default_value

# Configure logging
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("AbletonMCPServer")

@dataclass
class AbletonConnection:
    host: str
    port: int
    sock: socket.socket = None

    def connect(self) -> bool:
        """Connect to the Ableton Remote Script socket server"""
        if self.sock:
            return True

        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.connect((self.host, self.port))
            logger.info(f"Connected to Ableton at {self.host}:{self.port}")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to Ableton: {str(e)}")
            self.sock = None
            return False

    def disconnect(self):
        """Disconnect from the Ableton Remote Script"""
        if self.sock:
            try:
                self.sock.close()
            except Exception as e:
                logger.error(f"Error disconnecting from Ableton: {str(e)}")
            finally:
                self.sock = None

    def receive_full_response(self, sock, buffer_size=8192):
        """Receive the complete response, potentially in multiple chunks"""
        chunks = []
        sock.settimeout(15.0)  # Increased timeout for operations that might take longer

        try:
            while True:
                try:
                    chunk = sock.recv(buffer_size)
                    if not chunk:
                        if not chunks:
                            raise Exception("Connection closed before receiving any data")
                        break

                    chunks.append(chunk)

                    # Check if we've received a complete JSON object
                    try:
                        data = b''.join(chunks)
                        json.loads(data.decode('utf-8'))
                        logger.info(f"Received complete response ({len(data)} bytes)")
                        return data
                    except json.JSONDecodeError:
                        # Incomplete JSON, continue receiving
                        continue
                except socket.timeout:
                    logger.warning("Socket timeout during chunked receive")
                    break
                except (ConnectionError, BrokenPipeError, ConnectionResetError) as e:
                    logger.error(f"Socket connection error during receive: {str(e)}")
                    raise
        except Exception as e:
            logger.error(f"Error during receive: {str(e)}")
            raise

        # If we get here, we either timed out or broke out of the loop
        if chunks:
            data = b''.join(chunks)
            logger.info(f"Returning data after receive completion ({len(data)} bytes)")
            try:
                json.loads(data.decode('utf-8'))
                return data
            except json.JSONDecodeError:
                raise Exception("Incomplete JSON response received")
        else:
            raise Exception("No data received")

    def send_command(self, command_type: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
        """Send a command to Ableton and return the response"""
        if not self.sock and not self.connect():
            raise ConnectionError("Not connected to Ableton")

        command = {
            "type": command_type,
            "params": params or {}
        }

        # Check if this is a state-modifying command
        is_modifying_command = command_type in [
            "create_midi_track", "create_audio_track", "set_track_name",
            "create_clip", "add_notes_to_clip", "set_clip_name",
            "set_tempo", "set_signature_denominator", "set_signature_numerator",
            "fire_clip", "stop_clip", "set_device_parameter",
            "start_playback", "stop_playback", "load_instrument_or_effect",
            # Arrangement/transport additions
            "set_record_mode", "continue_playing", "jump_by", "set_back_to_arranger",
            "set_start_time", "set_metronome", "set_clip_trigger_quantization",
            "set_loop", "set_loop_region", "play_selection", "jump_to_next_cue",
            "jump_to_prev_cue", "toggle_cue_at_current", "re_enable_automation",
            "set_arrangement_overdub", "set_session_automation_record",
            "trigger_session_record", "create_locator", "set_song_position", "set_send_level",
            # New arrangement layout helpers
            "duplicate_track_clip_to_arrangement", "clear_arrangement",
            "rename_cue_point", "set_current_song_time_beats", "stop_all_clips",
            "jump_to_cue", "jump_by_beats",
            # Application.View actions
            "application_view_focus_view", "application_view_hide_view",
            "application_view_scroll_view", "application_view_show_view",
            "application_view_toggle_browse", "application_view_zoom_view"
        ]

        try:
            logger.info(f"Sending command: {command_type} with params: {params}")

            # Send the command
            self.sock.sendall(json.dumps(command).encode('utf-8'))
            logger.info(f"Command sent, waiting for response...")

            # For state-modifying commands, add a small delay to give Ableton time to process
            if is_modifying_command:
                import time
                time.sleep(0.1)  # 100ms delay

            # Set timeout based on command type
            timeout = 15.0 if is_modifying_command else 10.0
            self.sock.settimeout(timeout)

            # Receive the response
            response_data = self.receive_full_response(self.sock)
            logger.info(f"Received {len(response_data)} bytes of data")

            # Parse the response
            response = json.loads(response_data.decode('utf-8'))
            logger.info(f"Response parsed, status: {response.get('status', 'unknown')}")

            if response.get("status") == "error":
                logger.error(f"Ableton error: {response.get('message')}")
                raise Exception(response.get("message", "Unknown error from Ableton"))

            # For state-modifying commands, add another small delay after receiving response
            if is_modifying_command:
                import time
                time.sleep(0.1)  # 100ms delay

            return response.get("result", {})
        except socket.timeout:
            logger.error("Socket timeout while waiting for response from Ableton")
            self.sock = None
            raise Exception("Timeout waiting for Ableton response")
        except (ConnectionError, BrokenPipeError, ConnectionResetError) as e:
            logger.error(f"Socket connection error: {str(e)}")
            self.sock = None
            raise Exception(f"Connection to Ableton lost: {str(e)}")
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON response from Ableton: {str(e)}")
            if 'response_data' in locals() and response_data:
                logger.error(f"Raw response (first 200 bytes): {response_data[:200]}")
            self.sock = None
            raise Exception(f"Invalid response from Ableton: {str(e)}")
        except Exception as e:
            logger.error(f"Error communicating with Ableton: {str(e)}")
            self.sock = None
            raise Exception(f"Communication error with Ableton: {str(e)}")

@asynccontextmanager
async def server_lifespan(server: FastMCP) -> AsyncIterator[Dict[str, Any]]:
    """Manage server startup and shutdown lifecycle"""
    try:
        logger.info("AbletonMCP server starting up")

        try:
            ableton = get_ableton_connection()
            logger.info("Successfully connected to Ableton on startup")
        except Exception as e:
            logger.warning(f"Could not connect to Ableton on startup: {str(e)}")
            logger.warning("Make sure the Ableton Remote Script is running")

        yield {}
    finally:
        global _ableton_connection
        if _ableton_connection:
            logger.info("Disconnecting from Ableton on shutdown")
            _ableton_connection.disconnect()
            _ableton_connection = None
        logger.info("AbletonMCP server shut down")

# Create the MCP server with lifespan support
mcp = FastMCP(
    "AbletonMCP",
    description="Ableton Live integration through the Model Context Protocol",
    lifespan=server_lifespan
)

# Global connection for resources
_ableton_connection = None

def get_ableton_connection():
    """Get or create a persistent Ableton connection"""
    global _ableton_connection

    if _ableton_connection is not None:
        try:
            # Test the connection with a simple ping
            # We'll try to send an empty message, which should fail if the connection is dead
            # but won't affect Ableton if it's alive
            _ableton_connection.sock.settimeout(1.0)
            _ableton_connection.sock.sendall(b'')
            return _ableton_connection
        except Exception as e:
            logger.warning(f"Existing connection is no longer valid: {str(e)}")
            try:
                _ableton_connection.disconnect()
            except:
                pass
            _ableton_connection = None

    # Connection doesn't exist or is invalid, create a new one
    if _ableton_connection is None:
        # Try to connect up to 3 times with a short delay between attempts
        max_attempts = 3
        for attempt in range(1, max_attempts + 1):
            try:
                logger.info(f"Connecting to Ableton (attempt {attempt}/{max_attempts})...")
                _ableton_connection = AbletonConnection(host="localhost", port=9877)
                if _ableton_connection.connect():
                    logger.info("Created new persistent connection to Ableton")

                    # Validate connection with a simple command
                    try:
                        # Get session info as a test
                        _ableton_connection.send_command("get_session_info")
                        logger.info("Connection validated successfully")
                        return _ableton_connection
                    except Exception as e:
                        logger.error(f"Connection validation failed: {str(e)}")
                        _ableton_connection.disconnect()
                        _ableton_connection = None
                        # Continue to next attempt
                else:
                    _ableton_connection = None
            except Exception as e:
                logger.error(f"Connection attempt {attempt} failed: {str(e)}")
                if _ableton_connection:
                    _ableton_connection.disconnect()
                    _ableton_connection = None

            # Wait before trying again, but only if we have more attempts left
            if attempt < max_attempts:
                import time
                time.sleep(1.0)

        # If we get here, all connection attempts failed
        if _ableton_connection is None:
            logger.error("Failed to connect to Ableton after multiple attempts")
            raise Exception("Could not connect to Ableton. Make sure the Remote Script is running.")

    return _ableton_connection


# Core Tool endpoints

@mcp.tool()
def get_session_info(ctx: Context) -> str:
    """Get detailed information about the current Ableton session"""
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("get_session_info")
        return json.dumps(result, indent=2)
    except Exception as e:
        logger.error(f"Error getting session info from Ableton: {str(e)}")
        return f"Error getting session info: {str(e)}"

@mcp.tool()
def get_application_info(ctx: Context) -> str:
    """Get information about the Live Application (LOM Application)."""
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("get_application_info")
        return json.dumps(result, indent=2)
    except Exception as e:
        logger.error(f"Error getting application info: {str(e)}")
        return f"Error getting application info: {str(e)}"

@mcp.tool()
def get_application_view_state(ctx: Context) -> str:
    """Get Application.View properties: browse_mode and focused_document_view."""
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("get_application_view_state")
        return json.dumps(result, indent=2)
    except Exception as e:
        logger.error(f"Error getting application view state: {str(e)}")
        return f"Error getting application view state: {str(e)}"

@mcp.tool()
def get_application_process_usage(ctx: Context) -> str:
    """Get average and peak process usage from the Live Application."""
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("get_application_process_usage")
        return json.dumps(result, indent=2)
    except Exception as e:
        logger.error(f"Error getting application process usage: {str(e)}")
        return f"Error getting application process usage: {str(e)}"

@mcp.tool()
def get_application_version(ctx: Context) -> str:
    """Get version details from the Live Application (major/minor/bugfix/version_string)."""
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("get_application_version")
        return json.dumps(result, indent=2)
    except Exception as e:
        logger.error(f"Error getting application version: {str(e)}")
        return f"Error getting application version: {str(e)}"

@mcp.tool()
def get_application_document(ctx: Context) -> str:
    """Get a brief summary of the current Live Set via Application.get_document()."""
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("get_application_document")
        return json.dumps(result, indent=2)
    except Exception as e:
        logger.error(f"Error getting application document: {str(e)}")
        return f"Error getting application document: {str(e)}"

@mcp.tool()
def list_control_surfaces(ctx: Context) -> str:
    """List control surfaces configured in Live's preferences."""
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("list_control_surfaces")
        return json.dumps(result, indent=2)
    except Exception as e:
        logger.error(f"Error listing control surfaces: {str(e)}")
        return f"Error listing control surfaces: {str(e)}"

# Application.View tools

@mcp.tool()
def application_view_available_main_views(ctx: Context) -> str:
    """Return list of available main view names ('Browser', 'Arranger', 'Session', etc.)."""
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("application_view_available_main_views")
        return json.dumps(result, indent=2)
    except Exception as e:
        logger.error(f"Error getting available main views: {str(e)}")
        return f"Error getting available main views: {str(e)}"

@mcp.tool()
def application_view_focus_view(ctx: Context, view_name: str = "") -> str:
    """Shows named view and focuses on it. Empty string refers to the main window view."""
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("application_view_focus_view", {"view_name": view_name})
        return json.dumps(result, indent=2)
    except Exception as e:
        logger.error(f"Error focusing view: {str(e)}")
        return f"Error focusing view: {str(e)}"

@mcp.tool()
def application_view_hide_view(ctx: Context, view_name: str = "") -> str:
    """Hides the named view. Empty string refers to the main window view."""
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("application_view_hide_view", {"view_name": view_name})
        return json.dumps(result, indent=2)
    except Exception as e:
        logger.error(f"Error hiding view: {str(e)}")
        return f"Error hiding view: {str(e)}"

@mcp.tool()
def application_view_is_view_visible(ctx: Context, view_name: str) -> str:
    """Returns whether the specified view is currently visible."""
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("application_view_is_view_visible", {"view_name": view_name})
        return json.dumps(result, indent=2)
    except Exception as e:
        logger.error(f"Error checking view visibility: {str(e)}")
        return f"Error checking view visibility: {str(e)}"

@mcp.tool()
def application_view_scroll_view(ctx: Context, direction: int, view_name: str = "", modifier_pressed: bool = False) -> str:
    """Scroll the specified view. direction: 0=up,1=down,2=left,3=right; modifier affects Arranger behaviour."""
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("application_view_scroll_view", {"direction": direction, "view_name": view_name, "modifier_pressed": modifier_pressed})
        return json.dumps(result, indent=2)
    except Exception as e:
        logger.error(f"Error scrolling view: {str(e)}")
        return f"Error scrolling view: {str(e)}"

@mcp.tool()
def application_view_show_view(ctx: Context, view_name: str = "") -> str:
    """Shows the named view."""
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("application_view_show_view", {"view_name": view_name})
        return json.dumps(result, indent=2)
    except Exception as e:
        logger.error(f"Error showing view: {str(e)}")
        return f"Error showing view: {str(e)}"

@mcp.tool()
def application_view_toggle_browse(ctx: Context) -> str:
    """Displays device chain and browser and toggles Hot-Swap Mode for selected device."""
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("application_view_toggle_browse")
        return json.dumps(result, indent=2)
    except Exception as e:
        logger.error(f"Error toggling browse: {str(e)}")
        return f"Error toggling browse: {str(e)}"

@mcp.tool()
def application_view_zoom_view(ctx: Context, direction: int, view_name: str = "", modifier_pressed: bool = False) -> str:
    """Zoom the specified view. Only Arrangement and Session can be zoomed."""
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("application_view_zoom_view", {"direction": direction, "view_name": view_name, "modifier_pressed": modifier_pressed})
        return json.dumps(result, indent=2)
    except Exception as e:
        logger.error(f"Error zooming view: {str(e)}")
        return f"Error zooming view: {str(e)}"

@mcp.tool()
def press_current_dialog_button(ctx: Context, index: int) -> str:
    """Press the button with the given index in the current Live dialog box."""
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("press_current_dialog_button", {"index": index})
        return f"Pressed dialog button {result.get('index', index)}"
    except Exception as e:
        logger.error(f"Error pressing current dialog button: {str(e)}")
        return f"Error pressing current dialog button: {str(e)}"

@mcp.tool()
def get_track_info(ctx: Context, track_index: int) -> str:
    """
    Get detailed information about a specific track in Ableton.

    Parameters:
    - track_index: The index of the track to get information about
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("get_track_info", {"track_index": track_index})
        return json.dumps(result, indent=2)
    except Exception as e:
        logger.error(f"Error getting track info from Ableton: {str(e)}")
        return f"Error getting track info: {str(e)}"

@mcp.tool()
def list_scenes(ctx: Context) -> str:
    """Get a list of all scenes in the Ableton session."""
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("list_scenes")
        return json.dumps(result, indent=2)
    except Exception as e:
        logger.error(f"Error listing scenes: {str(e)}")
        return f"Error listing scenes: {str(e)}"

@mcp.tool()
def fire_scene(ctx: Context, scene_index: int) -> str:
    """
    Fire a scene in the Ableton session.

    Parameters:
    - scene_index: The index of the scene to fire.
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("fire_scene", {"scene_index": scene_index})
        return f"Fired scene {scene_index}."
    except Exception as e:
        logger.error(f"Error firing scene: {str(e)}")
        return f"Error firing scene: {str(e)}"

@mcp.tool()
def create_scene(ctx: Context, scene_index: int = -1) -> str:
    """
    Create a new scene in the Ableton session.

    Parameters:
    - scene_index: The index to create the scene at (-1 = end of list).
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("create_scene", {"scene_index": scene_index})
        new_index = result.get('scene_index', scene_index)
        return f"Created new scene at index {new_index}."
    except Exception as e:
        logger.error(f"Error creating scene: {str(e)}")
        return f"Error creating scene: {str(e)}"

@mcp.tool()
def rename_scene(ctx: Context, scene_index: int, name: str) -> str:
    """
    Rename a scene in the Ableton session.

    Parameters:
    - scene_index: The index of the scene to rename.
    - name: The new name for the scene.
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("rename_scene", {"scene_index": scene_index, "name": name})
        new_name = result.get('new_name', name)
        return f"Renamed scene {scene_index} to '{new_name}'."
    except Exception as e:
        logger.error(f"Error renaming scene: {str(e)}")
        return f"Error renaming scene: {str(e)}"

@mcp.tool()
def list_locators(ctx: Context) -> str:
    """Get a list of all locators (cue points) in the Ableton session."""
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("list_locators")
        return json.dumps(result, indent=2)
    except Exception as e:
        logger.error(f"Error listing locators: {str(e)}")
        return f"Error listing locators: {str(e)}"

@mcp.tool()
def list_return_tracks(ctx: Context) -> str:
    """Get a list of all return tracks in the Ableton session."""
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("list_return_tracks")
        return json.dumps(result, indent=2)
    except Exception as e:
        logger.error(f"Error listing return tracks: {str(e)}")
        return f"Error listing return tracks: {str(e)}"

@mcp.tool()
def set_send_level(ctx: Context, track_index: int, send_index: int, level: float) -> str:
    """
    Set the send level for a track.

    Parameters:
    - track_index: The index of the track to modify.
    - send_index: The index of the send to modify (corresponds to the return track index).
    - level: The new send level (0.0 to 1.0).
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("set_send_level", {
            "track_index": track_index,
            "send_index": send_index,
            "level": level
        })
        return f"Set send {send_index} on track {track_index} to {result.get('new_level')}."
    except Exception as e:
        logger.error(f"Error setting send level: {str(e)}")
        return f"Error setting send level: {str(e)}"

@mcp.tool()
def create_locator(ctx: Context, time: float) -> str:
    """
    Create a new locator (cue point) at a specific time in the arrangement.

    Parameters:
    - time: The time in beats where the locator should be created.
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("create_locator", {"time": time})
        return f"Created new locator at beat {result.get('time')}."
    except Exception as e:
        logger.error(f"Error creating locator: {str(e)}")
        return f"Error creating locator: {str(e)}"

@mcp.tool()
def set_song_position(ctx: Context, time: float) -> str:
    """
    Set the song's current playback time in the arrangement.

    Parameters:
    - time: The time in beats to set the playhead to.
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("set_song_position", {"time": time})
        return f"Song position set to beat {result.get('time')}."
    except Exception as e:
        logger.error(f"Error setting song position: {str(e)}")
        return f"Error setting song position: {str(e)}"

@mcp.tool()
def set_current_song_time_beats(ctx: Context, beats: float) -> str:
    """
    Write Song.current_song_time exactly in beats.
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("set_current_song_time_beats", {"beats": beats})
        return f"Current song time set to beat {result.get('time')}"
    except Exception as e:
        logger.error(f"Error setting current song time: {str(e)}")
        return f"Error setting current song time: {str(e)}"

# Arrangement and transport tools

@mcp.tool()
def set_record_mode(ctx: Context, on: bool) -> str:
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("set_record_mode", {"on": on})
        return f"Record mode set to {result.get('record_mode')}"
    except Exception as e:
        logger.error(f"Error setting record mode: {str(e)}")
        return f"Error setting record mode: {str(e)}"

@mcp.tool()
def continue_playing(ctx: Context) -> str:
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("continue_playing")
        return "Continuing playback"
    except Exception as e:
        logger.error(f"Error continuing playback: {str(e)}")
        return f"Error continuing playback: {str(e)}"

@mcp.tool()
def jump_by(ctx: Context, beats: float) -> str:
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("jump_by", {"beats": beats})
        return f"Jumped by {beats} beats"
    except Exception as e:
        logger.error(f"Error jumping by: {str(e)}")
        return f"Error jumping by: {str(e)}"

@mcp.tool()
def set_back_to_arranger(ctx: Context, on: bool) -> str:
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("set_back_to_arranger", {"on": on})
        return f"Back to Arranger set to {result.get('back_to_arranger')}"
    except Exception as e:
        logger.error(f"Error setting Back to Arranger: {str(e)}")
        return f"Error setting Back to Arranger: {str(e)}"

@mcp.tool()
def set_start_time(ctx: Context, beats: float) -> str:
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("set_start_time", {"beats": beats})
        return f"Start time set to {result.get('start_time')}"
    except Exception as e:
        logger.error(f"Error setting start time: {str(e)}")
        return f"Error setting start time: {str(e)}"

@mcp.tool()
def set_metronome(ctx: Context, on: bool) -> str:
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("set_metronome", {"on": on})
        return f"Metronome set to {result.get('metronome')}"
    except Exception as e:
        logger.error(f"Error setting metronome: {str(e)}")
        return f"Error setting metronome: {str(e)}"

@mcp.tool()
def set_clip_trigger_quantization(ctx: Context, quant: int) -> str:
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("set_clip_trigger_quantization", {"quant": quant})
        return f"Clip trigger quantization set to {result.get('clip_trigger_quantization')}"
    except Exception as e:
        logger.error(f"Error setting clip trigger quantization: {str(e)}")
        return f"Error setting clip trigger quantization: {str(e)}"

@mcp.tool()
def set_loop(ctx: Context, on: bool) -> str:
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("set_loop", {"on": on})
        return f"Loop set to {result.get('loop')}"
    except Exception as e:
        logger.error(f"Error setting loop: {str(e)}")
        return f"Error setting loop: {str(e)}"

@mcp.tool()
def set_loop_region(ctx: Context, start: float, length: float) -> str:
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("set_loop_region", {"start": start, "length": length})
        return f"Loop region set to start {result.get('loop_start')} length {result.get('loop_length')}"
    except Exception as e:
        logger.error(f"Error setting loop region: {str(e)}")
        return f"Error setting loop region: {str(e)}"

@mcp.tool()
def play_selection(ctx: Context) -> str:
    try:
        ableton = get_ableton_connection()
        ableton.send_command("play_selection")
        return "Playing selection"
    except Exception as e:
        logger.error(f"Error playing selection: {str(e)}")
        return f"Error playing selection: {str(e)}"

@mcp.tool()
def stop_all_clips(ctx: Context, quantized: int = 1) -> str:
    """
    Stop all Session clips. quantized=0 stops immediately.
    """
    try:
        ableton = get_ableton_connection()
        ableton.send_command("stop_all_clips", {"quantized": quantized})
        return "Stopped all clips"
    except Exception as e:
        logger.error(f"Error stopping all clips: {str(e)}")
        return f"Error stopping all clips: {str(e)}"

@mcp.tool()
def jump_to_next_cue(ctx: Context) -> str:
    try:
        ableton = get_ableton_connection()
        ableton.send_command("jump_to_next_cue")
        return "Jumped to next cue"
    except Exception as e:
        logger.error(f"Error jumping to next cue: {str(e)}")
        return f"Error jumping to next cue: {str(e)}"

@mcp.tool()
def jump_to_prev_cue(ctx: Context) -> str:
    try:
        ableton = get_ableton_connection()
        ableton.send_command("jump_to_prev_cue")
        return "Jumped to previous cue"
    except Exception as e:
        logger.error(f"Error jumping to previous cue: {str(e)}")
        return f"Error jumping to previous cue: {str(e)}"

@mcp.tool()
def jump_to_cue(ctx: Context, index: int) -> str:
    try:
        ableton = get_ableton_connection()
        ableton.send_command("jump_to_cue", {"index": index})
        return f"Jumped to cue {index}"
    except Exception as e:
        logger.error(f"Error jumping to cue: {str(e)}")
        return f"Error jumping to cue: {str(e)}"

@mcp.tool()
def toggle_cue_at_current(ctx: Context) -> str:
    try:
        ableton = get_ableton_connection()
        ableton.send_command("toggle_cue_at_current")
        return "Toggled cue at current position"
    except Exception as e:
        logger.error(f"Error toggling cue: {str(e)}")
        return f"Error toggling cue: {str(e)}"

@mcp.tool()
def re_enable_automation(ctx: Context) -> str:
    try:
        ableton = get_ableton_connection()
        ableton.send_command("re_enable_automation")
        return "Re-enabled automation"
    except Exception as e:
        logger.error(f"Error re-enabling automation: {str(e)}")
        return f"Error re-enabling automation: {str(e)}"

@mcp.tool()
def get_current_song_time_beats(ctx: Context) -> str:
    """
    Read back current song time in beats and formatted bars.beats.sixteenths.ticks.
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("get_current_song_time_beats")
        return json.dumps(result, indent=2)
    except Exception as e:
        logger.error(f"Error getting current song time: {str(e)}")
        return f"Error getting current song time: {str(e)}"

@mcp.tool()
def set_arrangement_overdub(ctx: Context, on: bool) -> str:
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("set_arrangement_overdub", {"on": on})
        return f"Arrangement overdub set to {result.get('arrangement_overdub')}"
    except Exception as e:
        logger.error(f"Error setting arrangement overdub: {str(e)}")
        return f"Error setting arrangement overdub: {str(e)}"

@mcp.tool()
def set_session_automation_record(ctx: Context, on: bool) -> str:
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("set_session_automation_record", {"on": on})
        return f"Session automation record set to {result.get('session_automation_record')}"
    except Exception as e:
        logger.error(f"Error setting session automation record: {str(e)}")
        return f"Error setting session automation record: {str(e)}"

@mcp.tool()
def trigger_session_record(ctx: Context, record_length: float = None) -> str:
    try:
        ableton = get_ableton_connection()
        params = {}
        if record_length is not None:
            params["record_length"] = record_length
        ableton.send_command("trigger_session_record", params)
        return "Triggered session record"
    except Exception as e:
        logger.error(f"Error triggering session record: {str(e)}")
        return f"Error triggering session record: {str(e)}"

@mcp.tool()
def rename_cue_point(ctx: Context, cue_index: int, name: str) -> str:
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("rename_cue_point", {"cue_index": cue_index, "name": name})
        return f"Renamed cue {cue_index} to '{result.get('new_name', name)}'"
    except Exception as e:
        logger.error(f"Error renaming cue point: {str(e)}")
        return f"Error renaming cue point: {str(e)}"

@mcp.tool()
def write_automation(
    ctx: Context,
    track_index: int,
    clip_index: int,
    device_index: int,
    points: List[Dict[str, float]],
    parameter_index: int = None,
    parameter_name: str = None
) -> str:
    """
    Write automation points for a device parameter within a clip.

    Parameters:
    - track_index: The index of the track.
    - clip_index: The index of the clip slot.
    - device_index: The index of the device on the track.
    - points: A list of automation points. Each point is a dictionary with "time" and "value" keys.
              Example: [{"time": 0.0, "value": 0.0}, {"time": 4.0, "value": 1.0}]
    - parameter_index: The index of the parameter to automate (optional).
    - parameter_name: The name of the parameter to automate (optional).
    """
    if parameter_index is None and parameter_name is None:
        return "Error: You must provide either a parameter_index or a parameter_name."

    try:
        ableton = get_ableton_connection()

        params = {
            "track_index": track_index,
            "clip_index": clip_index,
            "device_index": device_index,
            "points": points,
        }
        if parameter_index is not None:
            params["parameter_index"] = parameter_index
        if parameter_name is not None:
            params["parameter_name"] = parameter_name

        result = ableton.send_command("write_automation", params)
        point_count = result.get('point_count', len(points))
        param_name = result.get('parameter_name', 'Unknown')
        return f"Wrote {point_count} automation points for parameter '{param_name}'."
    except Exception as e:
        logger.error(f"Error writing automation: {str(e)}")
        return f"Error writing automation: {str(e)}"

@mcp.tool()
def create_midi_track(ctx: Context, index: int = -1) -> str:
    """
    Create a new MIDI track in the Ableton session.

    Parameters:
    - index: The index to insert the track at (-1 = end of list)
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("create_midi_track", {"index": index})
        return f"Created new MIDI track: {result.get('name', 'unknown')}"
    except Exception as e:
        logger.error(f"Error creating MIDI track: {str(e)}")
        return f"Error creating MIDI track: {str(e)}"

@mcp.tool()
def create_audio_track(ctx: Context, index: int = -1) -> str:
    """
    Create a new audio track in the Ableton session.

    Parameters:
    - index: The index to insert the track at (-1 = end of list)
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("create_audio_track", {"index": index})
        return f"Created new audio track: {result.get('name', 'unknown')}"
    except Exception as e:
        logger.error(f"Error creating audio track: {str(e)}")
        return f"Error creating audio track: {str(e)}"


@mcp.tool()
def set_track_name(ctx: Context, track_index: int, name: str) -> str:
    """
    Set the name of a track.

    Parameters:
    - track_index: The index of the track to rename
    - name: The new name for the track
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("set_track_name", {"track_index": track_index, "name": name})
        return f"Renamed track to: {result.get('name', name)}"
    except Exception as e:
        logger.error(f"Error setting track name: {str(e)}")
        return f"Error setting track name: {str(e)}"

@mcp.tool()
def create_clip(ctx: Context, track_index: int, clip_index: int, length: float = 4.0) -> str:
    """
    Create a new MIDI clip in the specified track and clip slot.

    Parameters:
    - track_index: The index of the track to create the clip in
    - clip_index: The index of the clip slot to create the clip in
    - length: The length of the clip in beats (default: 4.0)
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("create_clip", {
            "track_index": track_index,
            "clip_index": clip_index,
            "length": length
        })
        return f"Created new clip at track {track_index}, slot {clip_index} with length {length} beats"
    except Exception as e:
        logger.error(f"Error creating clip: {str(e)}")
        return f"Error creating clip: {str(e)}"

@mcp.tool()
def add_notes_to_clip(
    ctx: Context,
    track_index: int,
    clip_index: int,
    notes: List[Dict[str, Union[int, float, bool]]]
) -> str:
    """
    Add MIDI notes to a clip.

    Parameters:
    - track_index: The index of the track containing the clip
    - clip_index: The index of the clip slot containing the clip
    - notes: List of note dictionaries, each with pitch, start_time, duration, velocity, and mute
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("add_notes_to_clip", {
            "track_index": track_index,
            "clip_index": clip_index,
            "notes": notes
        })
        return f"Added {len(notes)} notes to clip at track {track_index}, slot {clip_index}"
    except Exception as e:
        logger.error(f"Error adding notes to clip: {str(e)}")
        return f"Error adding notes to clip: {str(e)}"

@mcp.tool()
def set_clip_name(ctx: Context, track_index: int, clip_index: int, name: str) -> str:
    """
    Set the name of a clip.

    Parameters:
    - track_index: The index of the track containing the clip
    - clip_index: The index of the clip slot containing the clip
    - name: The new name for the clip
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("set_clip_name", {
            "track_index": track_index,
            "clip_index": clip_index,
            "name": name
        })
        return f"Renamed clip at track {track_index}, slot {clip_index} to '{name}'"
    except Exception as e:
        logger.error(f"Error setting clip name: {str(e)}")
        return f"Error setting clip name: {str(e)}"

@mcp.tool()
def get_clip_info(ctx: Context, track_index: int, clip_index: int) -> str:
    """
    Get detailed information about a specific clip.

    Parameters:
    - track_index: The index of the track containing the clip.
    - clip_index: The index of the clip slot.
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("get_clip_info", {
            "track_index": track_index,
            "clip_index": clip_index
        })
        return json.dumps(result, indent=2)
    except Exception as e:
        logger.error(f"Error getting clip info: {str(e)}")
        return f"Error getting clip info: {str(e)}"

@mcp.tool()
def set_tempo(ctx: Context, tempo: float) -> str:
    """
    Set the tempo of the Ableton session.

    Parameters:
    - tempo: The new tempo in BPM
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("set_tempo", {"tempo": tempo})
        return f"Set tempo to {tempo} BPM"
    except Exception as e:
        logger.error(f"Error setting tempo: {str(e)}")
        return f"Error setting tempo: {str(e)}"

@mcp.tool()
def set_signature_denominator(ctx: Context, signature_denominator: int) -> str:
    """
    Set the time signature denominator of the song.

    Parameters:
    - signature_denominator: The new time signature denominator
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("set_signature_denominator", {"signature_denominator": signature_denominator})
        return f"Set signature denominator to {signature_denominator}"
    except Exception as e:
        logger.error(f"Error setting signature denominator: {str(e)}")
        return f"Error setting signature denominator: {str(e)}"

@mcp.tool()
def set_signature_numerator(ctx: Context, signature_numerator: int) -> str:
    """
    Set the time signature numerator of the song.

    Parameters:
    - signature_numerator: The new time signature numerator
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("set_signature_numerator", {"signature_numerator": signature_numerator})
        return f"Set signature numerator to {signature_numerator}"
    except Exception as e:
        logger.error(f"Error setting signature numerator: {str(e)}")
        return f"Error setting signature numerator: {str(e)}"

@mcp.tool()
def load_instrument_or_effect(ctx: Context, track_index: int, uri: str) -> str:
    """
    Load an instrument, effect, or audio file from the browser onto a track using its URI.

    Parameters:
    - track_index: The index of the track to load the item on.
    - uri: The URI of the browser item to load (e.g., an instrument, audio effect, or an audio file).
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("load_browser_item", {
            "track_index": track_index,
            "item_uri": uri
        })

        # Check if the instrument was loaded successfully
        if result.get("loaded", False):
            new_devices = result.get("new_devices", [])
            if new_devices:
                return f"Loaded instrument with URI '{uri}' on track {track_index}. New devices: {', '.join(new_devices)}"
            else:
                devices = result.get("devices_after", [])
                return f"Loaded instrument with URI '{uri}' on track {track_index}. Devices on track: {', '.join(devices)}"
        else:
            return f"Failed to load instrument with URI '{uri}'"
    except Exception as e:
        logger.error(f"Error loading instrument by URI: {str(e)}")
        return f"Error loading instrument by URI: {str(e)}"

@mcp.tool()
def fire_clip(ctx: Context, track_index: int, clip_index: int) -> str:
    """
    Start playing a clip.

    Parameters:
    - track_index: The index of the track containing the clip
    - clip_index: The index of the clip slot containing the clip
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("fire_clip", {
            "track_index": track_index,
            "clip_index": clip_index
        })
        return f"Started playing clip at track {track_index}, slot {clip_index}"
    except Exception as e:
        logger.error(f"Error firing clip: {str(e)}")
        return f"Error firing clip: {str(e)}"

@mcp.tool()
def stop_clip(ctx: Context, track_index: int, clip_index: int) -> str:
    """
    Stop playing a clip.

    Parameters:
    - track_index: The index of the track containing the clip
    - clip_index: The index of the clip slot containing the clip
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("stop_clip", {
            "track_index": track_index,
            "clip_index": clip_index
        })
        return f"Stopped clip at track {track_index}, slot {clip_index}"
    except Exception as e:
        logger.error(f"Error stopping clip: {str(e)}")
        return f"Error stopping clip: {str(e)}"

@mcp.tool()
def start_playback(ctx: Context) -> str:
    """Start playing the Ableton session."""
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("start_playback")
        return "Started playback"
    except Exception as e:
        logger.error(f"Error starting playback: {str(e)}")
        return f"Error starting playback: {str(e)}"

@mcp.tool()
def stop_playback(ctx: Context) -> str:
    """Stop playing the Ableton session."""
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("stop_playback")
        return "Stopped playback"
    except Exception as e:
        logger.error(f"Error stopping playback: {str(e)}")
        return f"Error stopping playback: {str(e)}"

@mcp.tool()
def get_device_parameters(ctx: Context, track_index: int, device_index: int) -> str:
    """
    Get a list of parameters for a specific device on a track.

    Parameters:
    - track_index: The index of the track containing the device.
    - device_index: The index of the device on the track.
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("get_device_parameters", {
            "track_index": track_index,
            "device_index": device_index
        })
        return json.dumps(result, indent=2)
    except Exception as e:
        logger.error(f"Error getting device parameters: {str(e)}")
        return f"Error getting device parameters: {str(e)}"

@mcp.tool()
def get_device_details(ctx: Context, track_index: int, device_index: int) -> str:
    """
    Get detailed information about a specific device on a track.

    Parameters:
    - track_index: The index of the track containing the device.
    - device_index: The index of the device on the track.
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("get_device_details", {
            "track_index": track_index,
            "device_index": device_index
        })
        return json.dumps(result, indent=2)
    except Exception as e:
        logger.error(f"Error getting device details: {str(e)}")
        return f"Error getting device details: {str(e)}"

@mcp.tool()
def find_device_by_name(ctx: Context, track_index: int, device_name: str) -> str:
    """
    Find the index of a device on a track by its name.

    Parameters:
    - track_index: The index of the track to search on.
    - device_name: The name of the device to find.
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("find_device_by_name", {
            "track_index": track_index,
            "device_name": device_name
        })
        if result.get("found"):
            return f"Device '{result.get('device_name')}' found at index {result.get('device_index')} on track {track_index}."
        else:
            return f"Device '{device_name}' not found on track {track_index}."
    except Exception as e:
        logger.error(f"Error finding device by name: {str(e)}")
        return f"Error finding device by name: {str(e)}"

@mcp.tool()
def set_device_parameter(
    ctx: Context,
    track_index: int,
    device_index: int,
    value: float,
    parameter_index: int = None,
    parameter_name: str = None
) -> str:
    """
    Set the value of a parameter for a specific device, identifying the parameter by its index or name.

    Parameters:
    - track_index: The index of the track containing the device.
    - device_index: The index of the device on the track.
    - value: The new value for the parameter.
    - parameter_index: The index of the parameter to set. Use this or parameter_name.
    - parameter_name: The name of the parameter to set. Use this or parameter_index.
    """
    if parameter_index is None and parameter_name is None:
        return "Error: You must provide either a parameter_index or a parameter_name."

    try:
        ableton = get_ableton_connection()

        params = {
            "track_index": track_index,
            "device_index": device_index,
            "value": value
        }
        if parameter_index is not None:
            params["parameter_index"] = parameter_index
        if parameter_name is not None:
            params["parameter_name"] = parameter_name

        result = ableton.send_command("set_device_parameter", params)

        return f"Set parameter '{result.get('parameter_name')}' on device {device_index} of track {track_index} to {result.get('new_value', value)}"
    except Exception as e:
        logger.error(f"Error setting device parameter: {str(e)}")
        return f"Error setting device parameter: {str(e)}"

@mcp.tool()
def delete_device(ctx: Context, track_index: int, device_index: int) -> str:
    """
    Delete a device from a track.

    Parameters:
    - track_index: The index of the track containing the device.
    - device_index: The index of the device to delete.
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("delete_device", {
            "track_index": track_index,
            "device_index": device_index
        })
        deleted_name = result.get('deleted_device_name', 'Unknown device')
        return f"Deleted device '{deleted_name}' from track {track_index}."
    except Exception as e:
        logger.error(f"Error deleting device: {str(e)}")
        return f"Error deleting device: {str(e)}"

@mcp.tool()
def clear_arrangement(ctx: Context, track_indices: List[int] = None) -> str:
    """
    Delete all arrangement clips on specified tracks or all tracks if None.
    """
    try:
        ableton = get_ableton_connection()
        params = {"track_indices": track_indices} if track_indices is not None else {}
        result = ableton.send_command("clear_arrangement", params)
        return json.dumps(result, indent=2)
    except Exception as e:
        logger.error(f"Error clearing arrangement: {str(e)}")
        return f"Error clearing arrangement: {str(e)}"

@mcp.tool()
def duplicate_track_clip_to_arrangement(
    ctx: Context,
    track_index: int,
    clip_index: int,
    start_beats: float,
    length_beats: float,
    loop: bool = None
) -> str:
    """
    Duplicate a Session clip to Arrangement at a given beat position and set its length/looping.
    """
    try:
        ableton = get_ableton_connection()
        params = {
            "track_index": track_index,
            "clip_index": clip_index,
            "start_beats": start_beats,
            "length_beats": length_beats
        }
        if loop is not None:
            params["loop"] = loop
        result = ableton.send_command("duplicate_track_clip_to_arrangement", params)
        return json.dumps(result, indent=2)
    except Exception as e:
        logger.error(f"Error duplicating session clip to arrangement: {str(e)}")
        return f"Error duplicating session clip to arrangement: {str(e)}"

@mcp.tool()
def get_browser_tree(ctx: Context, category_type: str = "all", max_depth: int = 2) -> str:
    """
    Get a hierarchical tree of browser categories from Ableton, with recursive exploration.

    Parameters:
    - category_type: Type of categories to get ('all', 'instruments', 'sounds', 'drums', 'audio_effects', 'midi_effects', 'plugins').
    - max_depth: How many levels of subfolders to explore. Defaults to 2.
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("get_browser_tree", {
            "category_type": category_type,
            "max_depth": max_depth
        })

        # Check if we got any categories
        if "available_categories" in result and len(result.get("categories", [])) == 0:
            available_cats = result.get("available_categories", [])
            return (f"No categories found for '{category_type}'. "
                   f"Available browser categories: {', '.join(available_cats)}")

        # Format the tree in a more readable way
        total_folders = result.get("total_folders", 0)
        formatted_output = f"Browser tree for '{category_type}' (showing {total_folders} folders):\n\n"

        def format_tree(item, indent=0):
            output = ""
            if item:
                prefix = "  " * indent
                name = item.get("name", "Unknown")
                path = item.get("path", "")
                has_more = item.get("has_more", False)

                # Add this item
                output += f"{prefix}• {name}"
                if path:
                    output += f" (path: {path})"
                if has_more:
                    output += " [...]"
                output += "\n"

                # Add children
                for child in item.get("children", []):
                    output += format_tree(child, indent + 1)
            return output

        # Format each category
        for category in result.get("categories", []):
            formatted_output += format_tree(category)
            formatted_output += "\n"

        return formatted_output
    except Exception as e:
        error_msg = str(e)
        if "Browser is not available" in error_msg:
            logger.error(f"Browser is not available in Ableton: {error_msg}")
            return f"Error: The Ableton browser is not available. Make sure Ableton Live is fully loaded and try again."
        elif "Could not access Live application" in error_msg:
            logger.error(f"Could not access Live application: {error_msg}")
            return f"Error: Could not access the Ableton Live application. Make sure Ableton Live is running and the Remote Script is loaded."
        else:
            logger.error(f"Error getting browser tree: {error_msg}")
            return f"Error getting browser tree: {error_msg}"

@mcp.tool()
def get_browser_items_at_path(ctx: Context, path: str) -> str:
    """
    Get browser items at a specific path in Ableton's browser.

    Parameters:
    - path: Path in the format "category/folder/subfolder"
            where category is one of the available browser categories in Ableton
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("get_browser_items_at_path", {
            "path": path
        })

        # Check if there was an error with available categories
        if "error" in result and "available_categories" in result:
            error = result.get("error", "")
            available_cats = result.get("available_categories", [])
            return (f"Error: {error}\n"
                   f"Available browser categories: {', '.join(available_cats)}")

        return json.dumps(result, indent=2)
    except Exception as e:
        error_msg = str(e)
        if "Browser is not available" in error_msg:
            logger.error(f"Browser is not available in Ableton: {error_msg}")
            return f"Error: The Ableton browser is not available. Make sure Ableton Live is fully loaded and try again."
        elif "Could not access Live application" in error_msg:
            logger.error(f"Could not access Live application: {error_msg}")
            return f"Error: Could not access the Ableton Live application. Make sure Ableton Live is running and the Remote Script is loaded."
        elif "Unknown or unavailable category" in error_msg:
            logger.error(f"Invalid browser category: {error_msg}")
            return f"Error: {error_msg}. Please check the available categories using get_browser_tree."
        elif "Path part" in error_msg and "not found" in error_msg:
            logger.error(f"Path not found: {error_msg}")
            return f"Error: {error_msg}. Please check the path and try again."
        else:
            logger.error(f"Error getting browser items at path: {error_msg}")
            return f"Error getting browser items at path: {error_msg}"

@mcp.tool()
def load_drum_kit(ctx: Context, track_index: int, rack_uri: str, kit_path: str) -> str:
    """
    Load a drum rack and then load a specific drum kit into it.

    Parameters:
    - track_index: The index of the track to load on
    - rack_uri: The URI of the drum rack to load (e.g., 'Drums/Drum Rack')
    - kit_path: Path to the drum kit inside the browser (e.g., 'drums/acoustic/kit1')
    """
    try:
        ableton = get_ableton_connection()

        # Step 1: Load the drum rack
        result = ableton.send_command("load_browser_item", {
            "track_index": track_index,
            "item_uri": rack_uri
        })

        if not result.get("loaded", False):
            return f"Failed to load drum rack with URI '{rack_uri}'"

        # Step 2: Get the drum kit items at the specified path
        kit_result = ableton.send_command("get_browser_items_at_path", {
            "path": kit_path
        })

        if "error" in kit_result:
            return f"Loaded drum rack but failed to find drum kit: {kit_result.get('error')}"

        # Step 3: Find a loadable drum kit
        kit_items = kit_result.get("items", [])
        loadable_kits = [item for item in kit_items if item.get("is_loadable", False)]

        if not loadable_kits:
            return f"Loaded drum rack but no loadable drum kits found at '{kit_path}'"

        # Step 4: Load the first loadable kit
        kit_uri = loadable_kits[0].get("uri")
        load_result = ableton.send_command("load_browser_item", {
            "track_index": track_index,
            "item_uri": kit_uri
        })

        return f"Loaded drum rack and kit '{loadable_kits[0].get('name')}' on track {track_index}"
    except Exception as e:
        logger.error(f"Error loading drum kit: {str(e)}")
        return f"Error loading drum kit: {str(e)}"

@mcp.tool()
def modify_m4l_device_default(
    ctx: Context,
    input_filepath: str,
    output_filepath: str,
    parameter_name: str,
    new_default_value: float
) -> str:
    """
    Creates a new Max for Live device file with a modified default value for a parameter.

    Parameters:
    - input_filepath: The path to the source .amxd file.
    - output_filepath: The path where the new .amxd file will be saved.
    - parameter_name: The name of the parameter to modify (e.g., "Decay", "Filter Freq").
    - new_default_value: The new default value for the parameter.
    """
    try:
        success = set_parameter_default_value(
            input_filepath,
            output_filepath,
            parameter_name,
            new_default_value
        )
        if success:
            return f"Successfully created new M4L device at '{output_filepath}' with updated default for '{parameter_name}'."
        else:
            # This path should ideally not be reached if set_parameter_default_value raises exceptions on failure
            return "An unknown error occurred during device modification."
    except Exception as e:
        logger.error(f"Error modifying M4L device: {str(e)}")
        return f"Error modifying M4L device: {str(e)}"

@mcp.tool()
def show_message(ctx: Context, message: str) -> str:
    """
    Display a message in Ableton's status bar.

    Parameters:
    - message: The message to display.
    """
    try:
        ableton = get_ableton_connection()
        ableton.send_command("show_message", {"message": message})
        return f"Message '{message}' shown in Ableton."
    except Exception as e:
        logger.error(f"Error showing message: {str(e)}")
        return f"Error showing message: {str(e)}"

# Main execution
def main():
    """Run the MCP server"""
    mcp.run()

if __name__ == "__main__":
    main()
