# AbletonMCP/init.py
from __future__ import absolute_import, print_function, unicode_literals

from _Framework.ControlSurface import ControlSurface
import socket
import json
import threading
import time
import traceback

# Change queue import for Python 2
try:
    import Queue as queue  # Python 2
except ImportError:
    import queue  # Python 3

# Constants for socket communication
DEFAULT_PORT = 9877
HOST = "localhost"

def create_instance(c_instance):
    """Create and return the AbletonMCP script instance"""
    return AbletonMCP(c_instance)

class AbletonMCP(ControlSurface):
    """AbletonMCP Remote Script for Ableton Live"""

    def __init__(self, c_instance):
        """Initialize the control surface"""
        ControlSurface.__init__(self, c_instance)
        self.log_message("AbletonMCP Remote Script initializing...")

        # Socket server for communication
        self.server = None
        self.client_threads = []
        self.server_thread = None
        self.running = False

        # Cache the song reference for easier access
        self._song = self.song()

        # Start the socket server
        self.start_server()

        self.log_message("AbletonMCP initialized")

        # Show a message in Ableton
        self.show_message("AbletonMCP: Listening for commands on port " + str(DEFAULT_PORT))

    def disconnect(self):
        """Called when Ableton closes or the control surface is removed"""
        self.log_message("AbletonMCP disconnecting...")
        self.running = False

        # Stop the server
        if self.server:
            try:
                self.server.close()
            except:
                pass

        # Wait for the server thread to exit
        if self.server_thread and self.server_thread.is_alive():
            self.server_thread.join(1.0)

        # Clean up any client threads
        for client_thread in self.client_threads[:]:
            if client_thread.is_alive():
                # We don't join them as they might be stuck
                self.log_message("Client thread still alive during disconnect")

        ControlSurface.disconnect(self)
        self.log_message("AbletonMCP disconnected")

    def start_server(self):
        """Start the socket server in a separate thread"""
        try:
            self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server.bind((HOST, DEFAULT_PORT))
            self.server.listen(5)  # Allow up to 5 pending connections

            self.running = True
            self.server_thread = threading.Thread(target=self._server_thread)
            self.server_thread.daemon = True
            self.server_thread.start()

            self.log_message("Server started on port " + str(DEFAULT_PORT))
        except Exception as e:
            self.log_message("Error starting server: " + str(e))
            self.show_message("AbletonMCP: Error starting server - " + str(e))

    def _server_thread(self):
        """Server thread implementation - handles client connections"""
        try:
            self.log_message("Server thread started")
            # Set a timeout to allow regular checking of running flag
            self.server.settimeout(1.0)

            while self.running:
                try:
                    # Accept connections with timeout
                    client, address = self.server.accept()
                    self.log_message("Connection accepted from " + str(address))
                    self.show_message("AbletonMCP: Client connected")

                    # Handle client in a separate thread
                    client_thread = threading.Thread(
                        target=self._handle_client,
                        args=(client,)
                    )
                    client_thread.daemon = True
                    client_thread.start()

                    # Keep track of client threads
                    self.client_threads.append(client_thread)

                    # Clean up finished client threads
                    self.client_threads = [t for t in self.client_threads if t.is_alive()]

                except socket.timeout:
                    # No connection yet, just continue
                    continue
                except Exception as e:
                    if self.running:  # Only log if still running
                        self.log_message("Server accept error: " + str(e))
                    time.sleep(0.5)

            self.log_message("Server thread stopped")
        except Exception as e:
            self.log_message("Server thread error: " + str(e))

    def _handle_client(self, client):
        """Handle communication with a connected client"""
        self.log_message("Client handler started")
        client.settimeout(None)  # No timeout for client socket
        buffer = ''  # Changed from b'' to '' for Python 2

        try:
            while self.running:
                try:
                    # Receive data
                    data = client.recv(8192)

                    if not data:
                        # Client disconnected
                        self.log_message("Client disconnected")
                        break

                    # Accumulate data in buffer with explicit encoding/decoding
                    try:
                        # Python 3: data is bytes, decode to string
                        buffer += data.decode('utf-8')
                    except AttributeError:
                        # Python 2: data is already string
                        buffer += data

                    try:
                        # Try to parse command from buffer
                        command = json.loads(buffer)  # Removed decode('utf-8')
                        buffer = ''  # Clear buffer after successful parse

                        self.log_message("Received command: " + str(command.get("type", "unknown")))

                        # Process the command and get response
                        response = self._process_command(command)

                        # Send the response with explicit encoding
                        try:
                            # Python 3: encode string to bytes
                            client.sendall(json.dumps(response).encode('utf-8'))
                        except AttributeError:
                            # Python 2: string is already bytes
                            client.sendall(json.dumps(response))
                    except ValueError:
                        # Incomplete data, wait for more
                        continue

                except Exception as e:
                    self.log_message("Error handling client data: " + str(e))
                    self.log_message(traceback.format_exc())

                    # Send error response if possible
                    error_response = {
                        "status": "error",
                        "message": str(e)
                    }
                    try:
                        # Python 3: encode string to bytes
                        client.sendall(json.dumps(error_response).encode('utf-8'))
                    except AttributeError:
                        # Python 2: string is already bytes
                        client.sendall(json.dumps(error_response))
                    except:
                        # If we can't send the error, the connection is probably dead
                        break

                    # For serious errors, break the loop
                    if not isinstance(e, ValueError):
                        break
        except Exception as e:
            self.log_message("Error in client handler: " + str(e))
        finally:
            try:
                client.close()
            except:
                pass
            self.log_message("Client handler stopped")

    def _process_command(self, command):
        """Process a command from the client and return a response"""
        command_type = command.get("type", "")
        params = command.get("params", {})

        # Initialize response
        response = {
            "status": "success",
            "result": {}
        }

        try:
            # Route the command to the appropriate handler
            if command_type == "get_session_info":
                response["result"] = self._get_session_info()
            elif command_type == "get_application_info":
                response["result"] = self._get_application_info()
            elif command_type == "get_application_view_state":
                response["result"] = self._get_application_view_state()
            elif command_type == "get_application_process_usage":
                response["result"] = self._get_application_process_usage()
            elif command_type == "get_application_version":
                response["result"] = self._get_application_version()
            elif command_type == "get_application_document":
                response["result"] = self._get_application_document()
            elif command_type == "list_control_surfaces":
                response["result"] = self._list_control_surfaces()
            elif command_type == "list_scenes":
                response["result"] = self._list_scenes()
            elif command_type == "get_track_info":
                track_index = params.get("track_index", 0)
                response["result"] = self._get_track_info(track_index)
            elif command_type == "get_device_details":
                track_index = params.get("track_index", 0)
                device_index = params.get("device_index", 0)
                response["result"] = self._get_device_details(track_index, device_index)
            elif command_type == "find_device_by_name":
                track_index = params.get("track_index", 0)
                device_name = params.get("device_name", "")
                response["result"] = self._find_device_by_name(track_index, device_name)
            elif command_type == "get_clip_info":
                track_index = params.get("track_index", 0)
                clip_index = params.get("clip_index", 0)
                response["result"] = self._get_clip_info(track_index, clip_index)
            elif command_type == "list_locators":
                response["result"] = self._list_locators()
            elif command_type == "list_return_tracks":
                response["result"] = self._list_return_tracks()
            # Commands that modify Live's state should be scheduled on the main thread
            elif command_type in ["create_midi_track", "create_audio_track", "set_track_name",
                                 "create_clip", "add_notes_to_clip", "set_clip_name",
                                 "set_tempo", "set_signature_denominator", "set_signature_numerator",
                                 "fire_clip", "stop_clip", "fire_scene",
                                 "create_scene", "rename_scene", "write_automation", "show_message",
                                 "create_locator", "set_song_position", "set_send_level",
                                 "start_playback", "stop_playback", "load_browser_item",
                                 "get_device_parameters", "set_device_parameter", "delete_device",
                                 # Arrangement/transport additions
                                 "set_record_mode", "continue_playing", "jump_by", "set_back_to_arranger",
                                 "set_start_time", "set_metronome", "set_clip_trigger_quantization",
                                 "set_loop", "set_loop_region", "play_selection", "jump_to_next_cue",
                                 "jump_to_prev_cue", "toggle_cue_at_current", "re_enable_automation",
                                 "set_arrangement_overdub", "set_session_automation_record",
                                 "trigger_session_record",
                                 # New arrangement layout helpers
                                 "duplicate_track_clip_to_arrangement", "clear_arrangement",
                                 "rename_cue_point", "set_current_song_time_beats", "stop_all_clips",
                                 "jump_to_cue", "jump_by_beats",
                                 # Application mutation
                                 "press_current_dialog_button",
                                 # Application.View functions
                                 "application_view_focus_view", "application_view_hide_view",
                                 "application_view_is_view_visible", "application_view_scroll_view",
                                 "application_view_show_view", "application_view_toggle_browse",
                                 "application_view_zoom_view", "application_view_available_main_views"]:
                # Use a thread-safe approach with a response queue
                response_queue = queue.Queue()

                # Define a function to execute on the main thread
                def main_thread_task():
                    try:
                        result = None
                        if command_type == "create_midi_track":
                            index = params.get("index", -1)
                            result = self._create_midi_track(index)
                        elif command_type == "create_audio_track":
                            index = params.get("index", -1)
                            result = self._create_audio_track(index)
                        elif command_type == "set_track_name":
                            track_index = params.get("track_index", 0)
                            name = params.get("name", "")
                            result = self._set_track_name(track_index, name)
                        elif command_type == "create_clip":
                            track_index = params.get("track_index", 0)
                            clip_index = params.get("clip_index", 0)
                            length = params.get("length", 4.0)
                            result = self._create_clip(track_index, clip_index, length)
                        elif command_type == "add_notes_to_clip":
                            track_index = params.get("track_index", 0)
                            clip_index = params.get("clip_index", 0)
                            notes = params.get("notes", [])
                            result = self._add_notes_to_clip(track_index, clip_index, notes)
                        elif command_type == "set_clip_name":
                            track_index = params.get("track_index", 0)
                            clip_index = params.get("clip_index", 0)
                            name = params.get("name", "")
                            result = self._set_clip_name(track_index, clip_index, name)
                        elif command_type == "set_tempo":
                            tempo = params.get("tempo", 120.0)
                            result = self._set_tempo(tempo)
                        elif command_type == "set_signature_denominator":
                            signature_denominator = params.get("signature_denominator", 4)
                            result = self._set_signature_denominator(signature_denominator)
                        elif command_type == "set_signature_numerator":
                            signature_numerator = params.get("signature_numerator", 4)
                            result = self._set_signature_numerator(signature_numerator)
                        elif command_type == "fire_clip":
                            track_index = params.get("track_index", 0)
                            clip_index = params.get("clip_index", 0)
                            result = self._fire_clip(track_index, clip_index)
                        elif command_type == "stop_clip":
                            track_index = params.get("track_index", 0)
                            clip_index = params.get("clip_index", 0)
                            result = self._stop_clip(track_index, clip_index)
                        elif command_type == "fire_scene":
                            scene_index = params.get("scene_index", 0)
                            result = self._fire_scene(scene_index)
                        elif command_type == "create_scene":
                            scene_index = params.get("scene_index", -1)
                            result = self._create_scene(scene_index)
                        elif command_type == "rename_scene":
                            scene_index = params.get("scene_index", 0)
                            name = params.get("name", "")
                            result = self._rename_scene(scene_index, name)
                        elif command_type == "create_locator":
                            time = params.get("time", 0.0)
                            result = self._create_locator(time)
                        elif command_type == "set_song_position":
                            time = params.get("time", 0.0)
                            result = self._set_song_position(time)
                        elif command_type == "set_current_song_time_beats":
                            beats = params.get("beats", 0.0)
                            result = self._set_current_song_time_beats(beats)
                        elif command_type == "set_send_level":
                            track_index = params.get("track_index", 0)
                            send_index = params.get("send_index", 0)
                            level = params.get("level", 0.0)
                            result = self._set_send_level(track_index, send_index, level)
                        elif command_type == "write_automation":
                            params_to_pass = params.copy()
                            result = self._write_automation(**params_to_pass)
                        elif command_type == "show_message":
                            message = params.get("message", "")
                            result = self._show_message(message)
                        elif command_type == "start_playback":
                            result = self._start_playback()
                        elif command_type == "stop_playback":
                            result = self._stop_playback()
                        elif command_type == "load_browser_item":
                            track_index = params.get("track_index", 0)
                            item_uri = params.get("item_uri", "")
                            result = self._load_browser_item(track_index, item_uri)
                        elif command_type == "set_record_mode":
                            on = params.get("on", False)
                            result = self._set_record_mode(on)
                        elif command_type == "continue_playing":
                            result = self._continue_playing()
                        elif command_type == "jump_by":
                            beats = params.get("beats", 0.0)
                            result = self._jump_by(beats)
                        elif command_type == "jump_by_beats":
                            beats = params.get("beats", 0.0)
                            result = self._jump_by(beats)
                        elif command_type == "set_back_to_arranger":
                            on = params.get("on", False)
                            result = self._set_back_to_arranger(on)
                        elif command_type == "set_start_time":
                            beats = params.get("beats", 0.0)
                            result = self._set_start_time(beats)
                        elif command_type == "set_metronome":
                            on = params.get("on", False)
                            result = self._set_metronome(on)
                        elif command_type == "set_clip_trigger_quantization":
                            quant = params.get("quant", 4)
                            result = self._set_clip_trigger_quantization(quant)
                        elif command_type == "set_loop":
                            on = params.get("on", False)
                            result = self._set_loop(on)
                        elif command_type == "set_loop_region":
                            start = params.get("start", 0.0)
                            length = params.get("length", 0.0)
                            result = self._set_loop_region(start, length)
                        elif command_type == "play_selection":
                            result = self._play_selection()
                        elif command_type == "jump_to_next_cue":
                            result = self._jump_to_next_cue()
                        elif command_type == "jump_to_prev_cue":
                            result = self._jump_to_prev_cue()
                        elif command_type == "jump_to_cue":
                            index = params.get("index", 0)
                            result = self._jump_to_cue(index)
                        elif command_type == "toggle_cue_at_current":
                            result = self._toggle_cue_at_current()
                        elif command_type == "re_enable_automation":
                            result = self._re_enable_automation()
                        elif command_type == "set_arrangement_overdub":
                            on = params.get("on", False)
                            result = self._set_arrangement_overdub(on)
                        elif command_type == "set_session_automation_record":
                            on = params.get("on", False)
                            result = self._set_session_automation_record(on)
                        elif command_type == "trigger_session_record":
                            record_length = params.get("record_length")
                            result = self._trigger_session_record(record_length)
                        elif command_type == "duplicate_track_clip_to_arrangement":
                            track_index = params.get("track_index", 0)
                            clip_index = params.get("clip_index", 0)
                            start_beats = params.get("start_beats", 0.0)
                            length_beats = params.get("length_beats", 0.0)
                            loop = params.get("loop")
                            result = self._duplicate_track_clip_to_arrangement(track_index, clip_index, start_beats, length_beats, loop)
                        elif command_type == "clear_arrangement":
                            track_indices = params.get("track_indices")
                            result = self._clear_arrangement(track_indices)
                        elif command_type == "rename_cue_point":
                            cue_index = params.get("cue_index", 0)
                            name = params.get("name", "")
                            result = self._rename_cue_point(cue_index, name)
                        elif command_type == "stop_all_clips":
                            quantized = params.get("quantized", 1)
                            result = self._stop_all_clips(quantized)
                        elif command_type == "get_device_parameters":
                            track_index = params.get("track_index", 0)
                            device_index = params.get("device_index", 0)
                            result = self._get_device_parameters(track_index, device_index)
                        elif command_type == "set_device_parameter":
                            track_index = params.get("track_index", 0)
                            device_index = params.get("device_index", 0)
                            value = params.get("value", 0)
                            parameter_index = params.get("parameter_index")
                            parameter_name = params.get("parameter_name")
                            result = self._set_device_parameter(track_index, device_index, value, parameter_index, parameter_name)
                        elif command_type == "delete_device":
                            track_index = params.get("track_index", 0)
                            device_index = params.get("device_index", 0)
                            result = self._delete_device(track_index, device_index)
                        elif command_type == "press_current_dialog_button":
                            index = params.get("index", 0)
                            result = self._press_current_dialog_button(index)
                        # Application.View operations
                        elif command_type == "application_view_available_main_views":
                            result = self._application_view_available_main_views()
                        elif command_type == "application_view_focus_view":
                            view_name = params.get("view_name", "")
                            result = self._application_view_focus_view(view_name)
                        elif command_type == "application_view_hide_view":
                            view_name = params.get("view_name", "")
                            result = self._application_view_hide_view(view_name)
                        elif command_type == "application_view_is_view_visible":
                            view_name = params.get("view_name", "")
                            result = self._application_view_is_view_visible(view_name)
                        elif command_type == "application_view_scroll_view":
                            direction = int(params.get("direction", 0))
                            view_name = params.get("view_name", "")
                            modifier_pressed = bool(params.get("modifier_pressed", False))
                            result = self._application_view_scroll_view(direction, view_name, modifier_pressed)
                        elif command_type == "application_view_show_view":
                            view_name = params.get("view_name", "")
                            result = self._application_view_show_view(view_name)
                        elif command_type == "application_view_toggle_browse":
                            result = self._application_view_toggle_browse()
                        elif command_type == "application_view_zoom_view":
                            direction = int(params.get("direction", 0))
                            view_name = params.get("view_name", "")
                            modifier_pressed = bool(params.get("modifier_pressed", False))
                            result = self._application_view_zoom_view(direction, view_name, modifier_pressed)

                        # Put the result in the queue
                        response_queue.put({"status": "success", "result": result})
                    except Exception as e:
                        self.log_message("Error in main thread task: " + str(e))
                        self.log_message(traceback.format_exc())
                        response_queue.put({"status": "error", "message": str(e)})

                # Schedule the task to run on the main thread
                try:
                    self.schedule_message(0, main_thread_task)
                except AssertionError:
                    # If we're already on the main thread, execute directly
                    main_thread_task()

                # Wait for the response with a timeout
                try:
                    task_response = response_queue.get(timeout=10.0)
                    if task_response.get("status") == "error":
                        response["status"] = "error"
                        response["message"] = task_response.get("message", "Unknown error")
                    else:
                        response["result"] = task_response.get("result", {})
                except queue.Empty:
                    response["status"] = "error"
                    response["message"] = "Timeout waiting for operation to complete"
            elif command_type == "get_browser_item":
                uri = params.get("uri", None)
                path = params.get("path", None)
                response["result"] = self._get_browser_item(uri, path)
            elif command_type == "get_browser_categories":
                category_type = params.get("category_type", "all")
                response["result"] = self._get_browser_categories(category_type)
            elif command_type == "get_browser_items":
                path = params.get("path", "")
                item_type = params.get("item_type", "all")
                response["result"] = self._get_browser_items(path, item_type)
            # Add the new browser commands
            elif command_type == "get_browser_tree":
                category_type = params.get("category_type", "all")
                max_depth = params.get("max_depth", 2)
                response["result"] = self.get_browser_tree(category_type, max_depth)
            elif command_type == "get_browser_items_at_path":
                path = params.get("path", "")
                response["result"] = self.get_browser_items_at_path(path)
            elif command_type == "get_current_song_time_beats":
                response["result"] = self._get_current_song_time_beats()
            else:
                response["status"] = "error"
                response["message"] = "Unknown command: " + command_type
        except Exception as e:
            self.log_message("Error processing command: " + str(e))
            self.log_message(traceback.format_exc())
            response["status"] = "error"
            response["message"] = str(e)

        return response

    # Command implementations

    def _get_session_info(self):
        """Get information about the current session"""
        try:
            result = {
                "tempo": self._song.tempo,
                "signature_numerator": self._song.signature_numerator,
                "signature_denominator": self._song.signature_denominator,
                "track_count": len(self._song.tracks),
                "return_track_count": len(self._song.return_tracks),
                "master_track": {
                    "name": "Master",
                    "volume": self._song.master_track.mixer_device.volume.value,
                    "panning": self._song.master_track.mixer_device.panning.value
                }
            }
            return result
        except Exception as e:
            self.log_message("Error getting session info: " + str(e))
            raise

    def _get_application_info(self):
        """Return basic information about the Live Application (LOM Application)."""
        try:
            app = self.application()
            if not app:
                raise RuntimeError("Could not access Live application")

            info = {
                "open_dialog_count": getattr(app, 'open_dialog_count', None),
                "current_dialog_message": getattr(app, 'current_dialog_message', None),
                "current_dialog_button_count": getattr(app, 'current_dialog_button_count', None),
                "average_process_usage": getattr(app, 'average_process_usage', None),
                "peak_process_usage": getattr(app, 'peak_process_usage', None),
                "has_browser": bool(getattr(app, 'browser', None)),
            }

            # Control surfaces summary (names may vary; fall back to class name)
            control_surfaces = []
            try:
                for cs in getattr(app, 'control_surfaces', []) or []:
                    try:
                        name = getattr(cs, 'name', None) or cs.__class__.__name__
                    except Exception:
                        name = 'UnknownControlSurface'
                    control_surfaces.append({
                        "class_name": cs.__class__.__name__,
                        "name": name
                    })
            except Exception:
                pass
            info["control_surfaces"] = control_surfaces
            info["control_surface_count"] = len(control_surfaces)

            return info
        except Exception as e:
            self.log_message("Error getting application info: " + str(e))
            raise

    def _get_application_view_state(self):
        """Return Application.View properties (browse_mode, focused_document_view)."""
        try:
            app = self.application()
            if not app:
                raise RuntimeError("Could not access Live application")
            view = getattr(app, 'view', None)
            if view is None:
                raise RuntimeError("Application.View not available")
            return {
                "browse_mode": getattr(view, 'browse_mode', None),
                "focused_document_view": getattr(view, 'focused_document_view', None)
            }
        except Exception as e:
            self.log_message("Error getting application view state: " + str(e))
            raise

    def _get_application_process_usage(self):
        """Return CPU/process usage reported by Live Application."""
        try:
            app = self.application()
            if not app:
                raise RuntimeError("Could not access Live application")
            return {
                "average_process_usage": getattr(app, 'average_process_usage', None),
                "peak_process_usage": getattr(app, 'peak_process_usage', None)
            }
        except Exception as e:
            self.log_message("Error getting application process usage: " + str(e))
            raise

    def _get_application_version(self):
        """Return version details from Live Application."""
        try:
            app = self.application()
            if not app:
                raise RuntimeError("Could not access Live application")
            version = {
                "version_string": None,
                "major": None,
                "minor": None,
                "bugfix": None,
            }
            try:
                version["version_string"] = app.get_version_string()
            except Exception:
                pass
            try:
                version["major"] = app.get_major_version()
            except Exception:
                pass
            try:
                version["minor"] = app.get_minor_version()
            except Exception:
                pass
            try:
                version["bugfix"] = app.get_bugfix_version()
            except Exception:
                pass
            return version
        except Exception as e:
            self.log_message("Error getting application version: " + str(e))
            raise

    def _get_application_document(self):
        """Return a brief summary of the current Live Set via Application.get_document()."""
        try:
            app = self.application()
            if not app:
                raise RuntimeError("Could not access Live application")
            doc = app.get_document()
            # Provide a minimal, stable summary
            return {
                "tempo": getattr(doc, 'tempo', None),
                "signature_numerator": getattr(doc, 'signature_numerator', None),
                "signature_denominator": getattr(doc, 'signature_denominator', None),
                "track_count": len(getattr(doc, 'tracks', [])),
                "scene_count": len(getattr(doc, 'scenes', [])),
            }
        except Exception as e:
            self.log_message("Error getting application document: " + str(e))
            raise

    def _list_control_surfaces(self):
        """List control surfaces configured in Live's preferences."""
        try:
            app = self.application()
            if not app:
                raise RuntimeError("Could not access Live application")
            items = []
            try:
                for idx, cs in enumerate(getattr(app, 'control_surfaces', []) or []):
                    try:
                        name = getattr(cs, 'name', None) or cs.__class__.__name__
                    except Exception:
                        name = cs.__class__.__name__
                    items.append({
                        "index": idx,
                        "class_name": cs.__class__.__name__,
                        "name": name,
                    })
            except Exception:
                pass
            return {"control_surfaces": items, "count": len(items)}
        except Exception as e:
            self.log_message("Error listing control surfaces: " + str(e))
            raise

    def _press_current_dialog_button(self, index):
        """Press a button in the current Live dialog by index (LOM Application.press_current_dialog_button)."""
        try:
            app = self.application()
            if not app:
                raise RuntimeError("Could not access Live application")
            idx = int(index)
            app.press_current_dialog_button(idx)
            return {"pressed": True, "index": idx}
        except Exception as e:
            self.log_message("Error pressing current dialog button: " + str(e))
            raise

    # Application.View methods
    def _application_view_available_main_views(self):
        """Return list of available main view names per LOM Application.View.available_main_views."""
        try:
            app = self.application()
            if not app:
                raise RuntimeError("Could not access Live application")
            view = getattr(app, 'view', None)
            if view is None:
                raise RuntimeError("Application.View not available")
            try:
                views = view.available_main_views()
            except Exception:
                # Some versions expose as property
                views = getattr(view, 'available_main_views', [])
            # Ensure list of strings
            try:
                return { "views": [str(v) for v in list(views or [])] }
            except Exception:
                return { "views": [] }
        except Exception as e:
            self.log_message("Error getting available main views: " + str(e))
            raise

    def _application_view_focus_view(self, view_name):
        try:
            app = self.application()
            if not app:
                raise RuntimeError("Could not access Live application")
            view = getattr(app, 'view', None)
            if view is None:
                raise RuntimeError("Application.View not available")
            view.focus_view(view_name)
            return { "focused_document_view": getattr(view, 'focused_document_view', None) }
        except Exception as e:
            self.log_message("Error focusing view: " + str(e))
            raise

    def _application_view_hide_view(self, view_name):
        try:
            app = self.application()
            if not app:
                raise RuntimeError("Could not access Live application")
            view = getattr(app, 'view', None)
            if view is None:
                raise RuntimeError("Application.View not available")
            view.hide_view(view_name)
            return { "hidden": True, "view_name": view_name }
        except Exception as e:
            self.log_message("Error hiding view: " + str(e))
            raise

    def _application_view_is_view_visible(self, view_name):
        try:
            app = self.application()
            if not app:
                raise RuntimeError("Could not access Live application")
            view = getattr(app, 'view', None)
            if view is None:
                raise RuntimeError("Application.View not available")
            visible = bool(view.is_view_visible(view_name))
            return { "visible": visible, "view_name": view_name }
        except Exception as e:
            self.log_message("Error checking view visibility: " + str(e))
            raise

    def _application_view_scroll_view(self, direction, view_name, modifier_pressed):
        try:
            app = self.application()
            if not app:
                raise RuntimeError("Could not access Live application")
            view = getattr(app, 'view', None)
            if view is None:
                raise RuntimeError("Application.View not available")
            view.scroll_view(int(direction), view_name, bool(modifier_pressed))
            return { "scrolled": True }
        except Exception as e:
            self.log_message("Error scrolling view: " + str(e))
            raise

    def _application_view_show_view(self, view_name):
        try:
            app = self.application()
            if not app:
                raise RuntimeError("Could not access Live application")
            view = getattr(app, 'view', None)
            if view is None:
                raise RuntimeError("Application.View not available")
            view.show_view(view_name)
            return { "shown": True, "view_name": view_name }
        except Exception as e:
            self.log_message("Error showing view: " + str(e))
            raise

    def _application_view_toggle_browse(self):
        try:
            app = self.application()
            if not app:
                raise RuntimeError("Could not access Live application")
            view = getattr(app, 'view', None)
            if view is None:
                raise RuntimeError("Application.View not available")
            view.toggle_browse()
            return { "toggled": True }
        except Exception as e:
            self.log_message("Error toggling browse: " + str(e))
            raise

    def _application_view_zoom_view(self, direction, view_name, modifier_pressed):
        try:
            app = self.application()
            if not app:
                raise RuntimeError("Could not access Live application")
            view = getattr(app, 'view', None)
            if view is None:
                raise RuntimeError("Application.View not available")
            view.zoom_view(int(direction), view_name, bool(modifier_pressed))
            return { "zoomed": True }
        except Exception as e:
            self.log_message("Error zooming view: " + str(e))
            raise

    def _get_track_info(self, track_index):
        """Get information about a track"""
        try:
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")

            track = self._song.tracks[track_index]

            # Get clip slots
            clip_slots = []
            for slot_index, slot in enumerate(track.clip_slots):
                clip_info = None
                if slot.has_clip:
                    clip = slot.clip
                    clip_info = {
                        "name": clip.name,
                        "length": clip.length,
                        "is_playing": clip.is_playing,
                        "is_recording": clip.is_recording
                    }

                clip_slots.append({
                    "index": slot_index,
                    "has_clip": slot.has_clip,
                    "clip": clip_info
                })

            # Get devices
            devices = []
            for device_index, device in enumerate(track.devices):
                devices.append({
                    "index": device_index,
                    "name": device.name,
                    "class_name": device.class_name,
                    "type": self._get_device_type(device)
                })

            result = {
                "index": track_index,
                "name": track.name,
                "is_audio_track": track.has_audio_input,
                "is_midi_track": track.has_midi_input,
                "mute": track.mute,
                "solo": track.solo,
                "arm": track.arm,
                "volume": track.mixer_device.volume.value,
                "panning": track.mixer_device.panning.value,
                "clip_slots": clip_slots,
                "devices": devices
            }
            return result
        except Exception as e:
            self.log_message("Error getting track info: " + str(e))
            raise

    def _list_scenes(self):
        """Get a list of all scenes in the session"""
        try:
            scenes = []
            for index, scene in enumerate(self._song.scenes):
                scenes.append({
                    "index": index,
                    "name": scene.name
                })
            return {
                "scenes": scenes,
                "scene_count": len(scenes)
            }
        except Exception as e:
            self.log_message("Error listing scenes: " + str(e))
            raise

    def _fire_scene(self, scene_index):
        """Fire a scene"""
        try:
            if scene_index < 0 or scene_index >= len(self._song.scenes):
                raise IndexError("Scene index out of range")

            scene = self._song.scenes[scene_index]
            scene.fire()

            return {
                "fired": True,
                "scene_index": scene_index
            }
        except Exception as e:
            self.log_message("Error firing scene: " + str(e))
            raise

    def _create_scene(self, scene_index):
        """Create a new scene"""
        try:
            # Create the scene at the specified index
            self._song.create_scene(scene_index)

            # Get the new scene's index
            new_scene_index = len(self._song.scenes) - 1 if scene_index == -1 else scene_index

            return {
                "created": True,
                "scene_index": new_scene_index
            }
        except Exception as e:
            self.log_message("Error creating scene: " + str(e))
            raise

    def _rename_scene(self, scene_index, name):
        """Rename a scene"""
        try:
            if scene_index < 0 or scene_index >= len(self._song.scenes):
                raise IndexError("Scene index out of range")

            scene = self._song.scenes[scene_index]
            scene.name = name

            return {
                "renamed": True,
                "scene_index": scene_index,
                "new_name": scene.name
            }
        except Exception as e:
            self.log_message("Error renaming scene: " + str(e))
            raise

    def _write_automation(self, track_index, clip_index, device_index, points, parameter_index=None, parameter_name=None):
        """Write automation points for a device parameter within a clip."""
        try:
            # 1. Get the clip
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")
            track = self._song.tracks[track_index]
            if clip_index < 0 or clip_index >= len(track.clip_slots):
                raise IndexError("Clip index out of range")
            clip_slot = track.clip_slots[clip_index]
            if not clip_slot.has_clip:
                raise ValueError("No clip in the specified slot.")
            clip = clip_slot.clip

            # 2. Get the device
            if device_index < 0 or device_index >= len(track.devices):
                raise IndexError("Device index out of range")
            device = track.devices[device_index]

            # 3. Get the parameter
            parameter = None
            if parameter_index is not None:
                if parameter_index < 0 or parameter_index >= len(device.parameters):
                    raise IndexError("Parameter index out of range")
                parameter = device.parameters[parameter_index]
            elif parameter_name is not None:
                for p in device.parameters:
                    if p.name.lower() == parameter_name.lower():
                        parameter = p
                        break
                if parameter is None:
                    raise ValueError("Parameter with name '{0}' not found".format(parameter_name))
            else:
                raise ValueError("Either parameter_index or parameter_name must be provided")

            if not parameter:
                raise ValueError("Parameter could not be found.")

            # 4. Get or create the automation envelope
            envelope = clip.get_automation_envelope(parameter)

            # 5. Set the automation points
            automation_points = []
            for point in points:
                automation_points.append((point.get("time"), point.get("value")))

            envelope.set_automation(tuple(automation_points))

            return {
                "wrote_automation": True,
                "point_count": len(automation_points),
                "parameter_name": parameter.name
            }
        except Exception as e:
            self.log_message("Error writing automation: " + str(e))
            raise

    def _create_midi_track(self, index):
        """Create a new MIDI track at the specified index"""
        try:
            # Create the track
            self._song.create_midi_track(index)

            # Get the new track
            new_track_index = len(self._song.tracks) - 1 if index == -1 else index
            new_track = self._song.tracks[new_track_index]

            result = {
                "index": new_track_index,
                "name": new_track.name
            }
            return result
        except Exception as e:
            self.log_message("Error creating MIDI track: " + str(e))
            raise

    def _create_audio_track(self, index):
        """Create a new audio track at the specified index"""
        try:
            # Create the track
            self._song.create_audio_track(index)

            # Get the new track
            new_track_index = len(self._song.tracks) - 1 if index == -1 else index
            new_track = self._song.tracks[new_track_index]

            result = {
                "index": new_track_index,
                "name": new_track.name
            }
            return result
        except Exception as e:
            self.log_message("Error creating audio track: " + str(e))
            raise

    def _set_track_name(self, track_index, name):
        """Set the name of a track"""
        try:
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")

            # Set the name
            track = self._song.tracks[track_index]
            track.name = name

            result = {
                "name": track.name
            }
            return result
        except Exception as e:
            self.log_message("Error setting track name: " + str(e))
            raise

    def _create_clip(self, track_index, clip_index, length):
        """Create a new MIDI clip in the specified track and clip slot"""
        try:
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")

            track = self._song.tracks[track_index]

            if clip_index < 0 or clip_index >= len(track.clip_slots):
                raise IndexError("Clip index out of range")

            clip_slot = track.clip_slots[clip_index]

            # Check if the clip slot already has a clip
            if clip_slot.has_clip:
                raise Exception("Clip slot already has a clip")

            # Create the clip
            clip_slot.create_clip(length)

            result = {
                "name": clip_slot.clip.name,
                "length": clip_slot.clip.length
            }
            return result
        except Exception as e:
            self.log_message("Error creating clip: " + str(e))
            raise

    def _add_notes_to_clip(self, track_index, clip_index, notes):
        """Add MIDI notes to a clip"""
        try:
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")

            track = self._song.tracks[track_index]

            if clip_index < 0 or clip_index >= len(track.clip_slots):
                raise IndexError("Clip index out of range")

            clip_slot = track.clip_slots[clip_index]

            if not clip_slot.has_clip:
                raise Exception("No clip in slot")

            clip = clip_slot.clip

            # Convert note data to Live's format
            live_notes = []
            for note in notes:
                pitch = note.get("pitch", 60)
                start_time = note.get("start_time", 0.0)
                duration = note.get("duration", 0.25)
                velocity = note.get("velocity", 100)
                mute = note.get("mute", False)

                live_notes.append((pitch, start_time, duration, velocity, mute))

            # Add the notes
            clip.set_notes(tuple(live_notes))

            result = {
                "note_count": len(notes)
            }
            return result
        except Exception as e:
            self.log_message("Error adding notes to clip: " + str(e))
            raise

    def _set_clip_name(self, track_index, clip_index, name):
        """Set the name of a clip"""
        try:
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")

            track = self._song.tracks[track_index]

            if clip_index < 0 or clip_index >= len(track.clip_slots):
                raise IndexError("Clip index out of range")

            clip_slot = track.clip_slots[clip_index]

            if not clip_slot.has_clip:
                raise Exception("No clip in slot")

            clip = clip_slot.clip
            clip.name = name

            result = {
                "name": clip.name
            }
            return result
        except Exception as e:
            self.log_message("Error setting clip name: " + str(e))
            raise

    def _set_tempo(self, tempo):
        """Set the tempo of the session"""
        try:
            self._song.tempo = tempo

            result = {
                "tempo": self._song.tempo
            }
            return result
        except Exception as e:
            self.log_message("Error setting tempo: " + str(e))
            raise

    def _set_signature_denominator(self, denom):
        """Set the time signature denominator of the song"""
        try:
            self._song.signature_denominator = denom

            result = {
                "signature_denominator": self._song.signature_denominator
            }
            return result
        except Exception as e:
            self.log_message("Error setting time signature denominator: " + str(e))
            raise

    def _set_signature_numerator(self, denom):
        """Set the time signature denominator of the song"""
        try:
            self._song.signature_numerator = denom

            result = {
                "signature_numerator": self._song.signature_denominator
            }
            return result
        except Exception as e:
            self.log_message("Error setting time signature numerator: " + str(e))
            raise

    def _fire_clip(self, track_index, clip_index):
        """Fire a clip"""
        try:
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")

            track = self._song.tracks[track_index]

            if clip_index < 0 or clip_index >= len(track.clip_slots):
                raise IndexError("Clip index out of range")

            clip_slot = track.clip_slots[clip_index]

            if not clip_slot.has_clip:
                raise Exception("No clip in slot")

            clip_slot.fire()

            result = {
                "fired": True
            }
            return result
        except Exception as e:
            self.log_message("Error firing clip: " + str(e))
            raise

    def _stop_clip(self, track_index, clip_index):
        """Stop a clip"""
        try:
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")

            track = self._song.tracks[track_index]

            if clip_index < 0 or clip_index >= len(track.clip_slots):
                raise IndexError("Clip index out of range")

            clip_slot = track.clip_slots[clip_index]

            clip_slot.stop()

            result = {
                "stopped": True
            }
            return result
        except Exception as e:
            self.log_message("Error stopping clip: " + str(e))
            raise


    def _start_playback(self):
        """Start playing the session"""
        try:
            self._song.start_playing()

            result = {
                "playing": self._song.is_playing
            }
            return result
        except Exception as e:
            self.log_message("Error starting playback: " + str(e))
            raise

    def _stop_playback(self):
        """Stop playing the session"""
        try:
            self._song.stop_playing()

            result = {
                "playing": self._song.is_playing
            }
            return result
        except Exception as e:
            self.log_message("Error stopping playback: " + str(e))
            raise

    def _get_browser_item(self, uri, path):
        """Get a browser item by URI or path"""
        try:
            # Access the application's browser instance instead of creating a new one
            app = self.application()
            if not app:
                raise RuntimeError("Could not access Live application")

            result = {
                "uri": uri,
                "path": path,
                "found": False
            }

            # Try to find by URI first if provided
            if uri:
                item = self._find_browser_item_by_uri(app.browser, uri)
                if item:
                    result["found"] = True
                    result["item"] = {
                        "name": item.name,
                        "is_folder": item.is_folder,
                        "is_device": item.is_device,
                        "is_loadable": item.is_loadable,
                        "uri": item.uri
                    }
                    return result

            # If URI not provided or not found, try by path
            if path:
                # Parse the path and navigate to the specified item
                path_parts = path.split("/")

                # Determine the root based on the first part
                current_item = None
                if path_parts[0].lower() == "nstruments":
                    current_item = app.browser.instruments
                elif path_parts[0].lower() == "sounds":
                    current_item = app.browser.sounds
                elif path_parts[0].lower() == "drums":
                    current_item = app.browser.drums
                elif path_parts[0].lower() == "audio_effects":
                    current_item = app.browser.audio_effects
                elif path_parts[0].lower() == "midi_effects":
                    current_item = app.browser.midi_effects
                else:
                    # Default to instruments if not specified
                    current_item = app.browser.instruments
                    # Don't skip the first part in this case
                    path_parts = ["instruments"] + path_parts

                # Navigate through the path
                for i in range(1, len(path_parts)):
                    part = path_parts[i]
                    if not part:  # Skip empty parts
                        continue

                    found = False
                    for child in current_item.children:
                        if child.name.lower() == part.lower():
                            current_item = child
                            found = True
                            break

                    if not found:
                        result["error"] = "Path part '{0}' not found".format(part)
                        return result

                # Found the item
                result["found"] = True
                result["item"] = {
                    "name": current_item.name,
                    "is_folder": current_item.is_folder,
                    "is_device": current_item.is_device,
                    "is_loadable": current_item.is_loadable,
                    "uri": current_item.uri
                }

            return result
        except Exception as e:
            self.log_message("Error getting browser item: " + str(e))
            self.log_message(traceback.format_exc())
            raise



    def _load_browser_item(self, track_index, item_uri):
        """Load a browser item onto a track by its URI"""
        try:
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")

            track = self._song.tracks[track_index]

            # Access the application's browser instance instead of creating a new one
            app = self.application()

            # Find the browser item by URI
            item = self._find_browser_item_by_uri(app.browser, item_uri)

            if not item:
                raise ValueError("Browser item with URI '{0}' not found".format(item_uri))

            # Select the track
            self._song.view.selected_track = track

            # Load the item
            app.browser.load_item(item)

            result = {
                "loaded": True,
                "item_name": item.name,
                "track_name": track.name,
                "uri": item_uri
            }
            return result
        except Exception as e:
            self.log_message("Error loading browser item: {0}".format(str(e)))
            self.log_message(traceback.format_exc())
            raise

    def _find_browser_item_by_uri(self, browser_or_item, uri, max_depth=10, current_depth=0):
        """Find a browser item by its URI"""
        try:
            # Check if this is the item we're looking for
            if hasattr(browser_or_item, 'uri') and browser_or_item.uri == uri:
                return browser_or_item

            # Stop recursion if we've reached max depth
            if current_depth >= max_depth:
                return None

            # Check if this is a browser with root categories
            if hasattr(browser_or_item, 'instruments'):
                # Check all main categories
                categories = [
                    browser_or_item.instruments,
                    browser_or_item.sounds,
                    browser_or_item.drums,
                    browser_or_item.audio_effects,
                    browser_or_item.midi_effects
                ]

                for category in categories:
                    item = self._find_browser_item_by_uri(category, uri, max_depth, current_depth + 1)
                    if item:
                        return item

                return None

            # Check if this item has children
            if hasattr(browser_or_item, 'children') and browser_or_item.children:
                for child in browser_or_item.children:
                    item = self._find_browser_item_by_uri(child, uri, max_depth, current_depth + 1)
                    if item:
                        return item

            return None
        except Exception as e:
            self.log_message("Error finding browser item by URI: {0}".format(str(e)))
            return None

    def _delete_device(self, track_index, device_index):
        """Delete a device from a track"""
        try:
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")

            track = self._song.tracks[track_index]

            if device_index < 0 or device_index >= len(track.devices):
                raise IndexError("Device index out of range")

            device_name = track.devices[device_index].name
            track.delete_device(device_index)

            return {
                "track_index": track_index,
                "device_index": device_index,
                "deleted_device_name": device_name
            }
        except Exception as e:
            self.log_message("Error deleting device: " + str(e))
            raise

    def _get_device_parameters(self, track_index, device_index):
        """Get a list of parameters for a device"""
        try:
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")

            track = self._song.tracks[track_index]

            if device_index < 0 or device_index >= len(track.devices):
                raise IndexError("Device index out of range")

            device = track.devices[device_index]

            parameters = []
            for param_index, param in enumerate(device.parameters):
                if param.is_enabled:
                    param_info = {
                        "index": param_index,
                        "name": param.name,
                        "value": param.value,
                        "min": param.min,
                        "max": param.max,
                        "is_quantized": param.is_quantized,
                    }
                    if param.is_quantized:
                        param_info["value_items"] = param.value_items
                    parameters.append(param_info)

            return {
                "track_index": track_index,
                "device_index": device_index,
                "device_name": device.name,
                "parameters": parameters
            }
        except Exception as e:
            self.log_message("Error getting device parameters: " + str(e))
            raise

    def _get_device_details(self, track_index, device_index):
        """Get detailed information about a specific device."""
        try:
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")
            track = self._song.tracks[track_index]

            if device_index < 0 or device_index >= len(track.devices):
                raise IndexError("Device index out of range")
            device = track.devices[device_index]

            details = {
                "name": device.name,
                "class_name": device.class_name,
                "type": self._get_device_type(device),
                "can_have_chains": device.can_have_chains,
                "can_have_drum_pads": device.can_have_drum_pads
            }
            return details
        except Exception as e:
            self.log_message("Error getting device details: " + str(e))
            raise

    def _find_device_by_name(self, track_index, device_name):
        """Find a device on a track by its name."""
        try:
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")
            track = self._song.tracks[track_index]

            for index, device in enumerate(track.devices):
                if device.name.lower() == device_name.lower():
                    return {
                        "found": True,
                        "track_index": track_index,
                        "device_index": index,
                        "device_name": device.name
                    }

            # If no device is found
            return {
                "found": False,
                "track_index": track_index,
                "device_name": device_name
            }
        except Exception as e:
            self.log_message("Error finding device by name: " + str(e))
            raise

    def _get_clip_info(self, track_index, clip_index):
        """Get detailed information about a specific clip."""
        try:
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")
            track = self._song.tracks[track_index]

            if clip_index < 0 or clip_index >= len(track.clip_slots):
                raise IndexError("Clip index out of range")
            clip_slot = track.clip_slots[clip_index]

            if not clip_slot.has_clip:
                return { "has_clip": False }

            clip = clip_slot.clip

            clip_details = {
                "has_clip": True,
                "name": clip.name,
                "color": clip.color,
                "is_looping": clip.looping,
                "loop_start": clip.loop_start,
                "loop_end": clip.loop_end,
                "start_marker": clip.start_marker,
                "end_marker": clip.end_marker,
                "signature_numerator": clip.signature_numerator,
                "signature_denominator": clip.signature_denominator,
                "is_playing": clip.is_playing,
            }
            return clip_details
        except Exception as e:
            self.log_message("Error getting clip info: " + str(e))
            raise

    def _show_message(self, message):
        """Display a message in Ableton's status bar."""
        try:
            self.show_message(message)
            return { "message_shown": True }
        except Exception as e:
            self.log_message("Error showing message: " + str(e))
            raise

    def _list_locators(self):
        """Get a list of all locators (cue points) in the session."""
        try:
            locators = []
            for cue_point in self._song.cue_points:
                locators.append({
                    "name": cue_point.name,
                    "time": cue_point.time
                })
            return {
                "locators": locators,
                "locator_count": len(locators)
            }
        except Exception as e:
            self.log_message("Error listing locators: " + str(e))
            raise

    def _list_return_tracks(self):
        """Get a list of all return tracks in the session."""
        try:
            return_tracks = []
            for index, track in enumerate(self._song.return_tracks):
                return_tracks.append({
                    "index": index,
                    "name": track.name
                })
            return {
                "return_tracks": return_tracks,
                "return_track_count": len(return_tracks)
            }
        except Exception as e:
            self.log_message("Error listing return tracks: " + str(e))
            raise

    def _set_send_level(self, track_index, send_index, level):
        """Set the send level for a track."""
        try:
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")
            track = self._song.tracks[track_index]

            if send_index < 0 or send_index >= len(track.mixer_device.sends):
                raise IndexError("Send index out of range")

            send = track.mixer_device.sends[send_index]
            send.value = level

            return {
                "send_set": True,
                "track_index": track_index,
                "send_index": send_index,
                "new_level": send.value
            }
        except Exception as e:
            self.log_message("Error setting send level: " + str(e))
            raise

    def _create_locator(self, time):
        """Create a new locator (cue point) at a specific beat using LOM-compliant behavior."""
        try:
            song = self._song
            # Prefer internal create_cue_point if present (not public LOM but may exist)
            if hasattr(song, 'create_cue_point'):
                cue = song.create_cue_point(time)
                return { "created": True, "time": cue.time }

            epsilon = 1e-4
            # If a cue already exists very near the requested time, just return it
            for cp in song.cue_points:
                if abs(cp.time - time) < epsilon:
                    return { "created": True, "time": cp.time }

            # Move the insert marker to desired time and toggle cue
            previous_time = song.current_song_time
            song.current_song_time = time
            song.set_or_delete_cue()  # Creates if none at current position

            # Verify and report
            created_time = None
            for cp in song.cue_points:
                if abs(cp.time - time) < epsilon:
                    created_time = cp.time
                    break
            if created_time is None:
                created_time = song.current_song_time
            # Restore previous position (non-critical)
            try:
                song.current_song_time = previous_time
            except:
                pass
            return { "created": True, "time": created_time }
        except Exception as e:
            self.log_message("Error creating locator: " + str(e))
            raise

    def _set_song_position(self, time):
        """Set the song's current playback time (beats)."""
        try:
            self._song.current_song_time = time
            measured = self._song.current_song_time
            return {
                "position_set": True,
                "requested_time": time,
                "time": measured
            }
        except Exception as e:
            self.log_message("Error setting song position: " + str(e))
            raise

    def _set_current_song_time_beats(self, beats):
        """Explicit setter for current_song_time in beats."""
        try:
            self._song.current_song_time = float(beats)
            return { "time": self._song.current_song_time }
        except Exception as e:
            self.log_message("Error setting current_song_time: " + str(e))
            raise

    def _get_current_song_time_beats(self):
        """Return current song time as float beats and bars.beats.sixteenths.ticks string."""
        try:
            # Ableton may return a BeatTime object from get_current_beats_song_time(),
            # which is not JSON serializable. Convert it to a string for transport.
            beat_time = self._song.get_current_beats_song_time()
            return {
                "current_song_time": self._song.current_song_time,
                "beats_string": str(beat_time)
            }
        except Exception as e:
            self.log_message("Error getting current song time: " + str(e))
            raise

    # Arrangement/transport helpers (LOM compliant)
    def _set_record_mode(self, on):
        try:
            self._song.record_mode = bool(on)
            return { "record_mode": self._song.record_mode }
        except Exception as e:
            self.log_message("Error setting record_mode: " + str(e))
            raise

    def _continue_playing(self):
        try:
            self._song.continue_playing()
            return { "playing": self._song.is_playing }
        except Exception as e:
            self.log_message("Error continue_playing: " + str(e))
            raise

    def _jump_by(self, beats):
        try:
            self._song.jump_by(float(beats))
            return { "current_song_time": self._song.current_song_time }
        except Exception as e:
            self.log_message("Error jump_by: " + str(e))
            raise

    def _set_back_to_arranger(self, on):
        try:
            self._song.back_to_arranger = bool(on)
            return { "back_to_arranger": self._song.back_to_arranger }
        except Exception as e:
            self.log_message("Error setting back_to_arranger: " + str(e))
            raise

    def _set_start_time(self, beats):
        try:
            self._song.start_time = float(beats)
            return { "start_time": self._song.start_time }
        except Exception as e:
            self.log_message("Error setting start_time: " + str(e))
            raise

    def _set_metronome(self, on):
        try:
            self._song.metronome = bool(on)
            return { "metronome": self._song.metronome }
        except Exception as e:
            self.log_message("Error setting metronome: " + str(e))
            raise

    def _set_clip_trigger_quantization(self, quant):
        try:
            self._song.clip_trigger_quantization = int(quant)
            return { "clip_trigger_quantization": self._song.clip_trigger_quantization }
        except Exception as e:
            self.log_message("Error setting clip_trigger_quantization: " + str(e))
            raise

    def _set_loop(self, on):
        try:
            self._song.loop = bool(on)
            return { "loop": self._song.loop }
        except Exception as e:
            self.log_message("Error setting loop: " + str(e))
            raise

    def _set_loop_region(self, start, length):
        try:
            self._song.loop_start = float(start)
            self._song.loop_length = float(length)
            return { "loop_start": self._song.loop_start, "loop_length": self._song.loop_length }
        except Exception as e:
            self.log_message("Error setting loop region: " + str(e))
            raise

    def _play_selection(self):
        try:
            self._song.play_selection()
            return { "playing": self._song.is_playing }
        except Exception as e:
            self.log_message("Error play_selection: " + str(e))
            raise

    def _jump_to_next_cue(self):
        try:
            self._song.jump_to_next_cue()
            return { "current_song_time": self._song.current_song_time }
        except Exception as e:
            self.log_message("Error jump_to_next_cue: " + str(e))
            raise

    def _jump_to_prev_cue(self):
        try:
            self._song.jump_to_prev_cue()
            return { "current_song_time": self._song.current_song_time }
        except Exception as e:
            self.log_message("Error jump_to_prev_cue: " + str(e))
            raise

    def _toggle_cue_at_current(self):
        try:
            self._song.set_or_delete_cue()
            return { "toggled": True }
        except Exception as e:
            self.log_message("Error set_or_delete_cue: " + str(e))
            raise

    def _jump_to_cue(self, index):
        """Jump to a specific cue point by index by setting current_song_time."""
        try:
            if index < 0 or index >= len(self._song.cue_points):
                raise IndexError("Cue index out of range")
            time_at_cue = self._song.cue_points[index].time
            self._song.current_song_time = time_at_cue
            return { "current_song_time": self._song.current_song_time }
        except Exception as e:
            self.log_message("Error jump_to_cue: " + str(e))
            raise

    def _re_enable_automation(self):
        try:
            self._song.re_enable_automation()
            return { "re_enabled": True }
        except Exception as e:
            self.log_message("Error re_enable_automation: " + str(e))
            raise

    def _set_arrangement_overdub(self, on):
        try:
            self._song.arrangement_overdub = bool(on)
            return { "arrangement_overdub": self._song.arrangement_overdub }
        except Exception as e:
            self.log_message("Error setting arrangement_overdub: " + str(e))
            raise

    def _set_session_automation_record(self, on):
        try:
            self._song.session_automation_record = bool(on)
            return { "session_automation_record": self._song.session_automation_record }
        except Exception as e:
            self.log_message("Error setting session_automation_record: " + str(e))
            raise

    def _trigger_session_record(self, record_length=None):
        try:
            if record_length is None:
                self._song.trigger_session_record()
            else:
                self._song.trigger_session_record(record_length)
            return { "session_record_triggered": True }
        except Exception as e:
            self.log_message("Error trigger_session_record: " + str(e))
            raise

    def _stop_all_clips(self, quantized=1):
        """Stop all session clips with optional quantization (1 by default)."""
        try:
            self._song.stop_all_clips(int(quantized))
            return { "stopped": True }
        except Exception as e:
            self.log_message("Error stop_all_clips: " + str(e))
            raise

    def _rename_cue_point(self, cue_index, name):
        """Rename a cue point by index."""
        try:
            if cue_index < 0 or cue_index >= len(self._song.cue_points):
                raise IndexError("Cue index out of range")
            self._song.cue_points[cue_index].name = name
            return { "cue_index": cue_index, "new_name": self._song.cue_points[cue_index].name }
        except Exception as e:
            self.log_message("Error rename_cue_point: " + str(e))
            raise

    def _clear_arrangement(self, track_indices=None):
        """Delete all arrangement clips on specified tracks or all tracks if None."""
        try:
            deleted_counts = []
            tracks_to_clear = []
            if track_indices is None:
                tracks_to_clear = list(self._song.tracks)
            else:
                for idx in track_indices:
                    if idx < 0 or idx >= len(self._song.tracks):
                        raise IndexError("Track index out of range: {0}".format(idx))
                    tracks_to_clear.append(self._song.tracks[idx])

            for t in tracks_to_clear:
                # Copy list to avoid mutation during iteration
                clips = list(getattr(t, 'arrangement_clips', []))
                count = 0
                for ac in clips:
                    try:
                        # ArrangementClip should support delete()
                        ac.delete()
                        count += 1
                    except Exception as e:
                        # Best effort; continue
                        self.log_message("Error deleting arrangement clip: " + str(e))
                deleted_counts.append(count)

            return { "tracks_cleared": len(tracks_to_clear), "deleted_counts": deleted_counts }
        except Exception as e:
            self.log_message("Error clearing arrangement: " + str(e))
            raise

    def _duplicate_track_clip_to_arrangement(self, track_index, clip_index, start_beats, length_beats, loop=None):
        """Duplicate a Session clip to Arrangement using Track.duplicate_clip_to_arrangement.

        This uses the documented API on Track rather than Clip. After duplication,
        length/loop is set if provided.
        """
        try:
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")
            track = self._song.tracks[track_index]
            if clip_index < 0 or clip_index >= len(track.clip_slots):
                raise IndexError("Clip index out of range")
            slot = track.clip_slots[clip_index]
            if not slot.has_clip:
                raise ValueError("No clip in the specified slot.")

            # Perform duplication using Track API
            try:
                new_arrangement_clip = track.duplicate_clip_to_arrangement(slot.clip, float(start_beats))
            except Exception as e:
                # Keep a helpful error message matching the LOM docs
                raise RuntimeError("Track.duplicate_clip_to_arrangement failed: {0}".format(str(e)))

            # If API returned the new clip use it
            if new_arrangement_clip is not None:
                # Collect state before changes for debugging
                def _state_dict(c):
                    def _g(name):
                        try:
                            return getattr(c, name)
                        except Exception as _e:
                            return "<err>"
                    return {
                        "start_time": _g("start_time"),
                        "end_time": _g("end_time"),
                        "looping": _g("looping"),
                        "loop_start": _g("loop_start"),
                        "loop_end": _g("loop_end"),
                        "start_marker": _g("start_marker"),
                        "end_marker": _g("end_marker"),
                        "is_arrangement_clip": _g("is_arrangement_clip"),
                        "is_session_clip": _g("is_session_clip"),
                        "length": _g("length"),
                    }

                pre_state = _state_dict(new_arrangement_clip)
                def _log_obj(label, obj):
                    try:
                        import json
                        s = json.dumps(obj, indent=2, ensure_ascii=False)
                        # Use larger chunks to reduce truncation in Live's status bar
                        max_len = 600
                        total = (len(s) + max_len - 1) // max_len
                        for i in range(total):
                            chunk = s[i * max_len:(i + 1) * max_len]
                            try:
                                self.log_message(f"{label} ({i+1}/{total}): " + chunk)
                            except Exception:
                                pass
                    except Exception:
                        try:
                            self.log_message(f"{label}: <unprintable>")
                        except Exception:
                            pass

                _log_obj("duplicate_to_arrangement pre", pre_state)

                # Determine the source clip unit length (Session clip length)
                try:
                    source_unit_length = float(getattr(slot.clip, 'length', 0.0))
                except Exception:
                    source_unit_length = 0.0
                if source_unit_length <= 0.0:
                    # Fallback to requested length or 4 beats if unknown
                    try:
                        source_unit_length = float(length_beats)
                    except Exception:
                        source_unit_length = 4.0

                # Set loop boundaries in a safe order to avoid
                # "LoopStart behind LoopEnd" errors from Live.
                # 1) Set loop_end first, then loop_start
                # 2) Apply the desired looping state (default True if not provided)
                desired_looping = True if loop is None else bool(loop)
                # Arrangement clip loop markers are clip-local, not absolute.
                # Loop the first segment in clip time: 0..segment_len
                loop_start_value = 0.0
                try:
                    total_length = float(length_beats)
                except Exception:
                    total_length = source_unit_length
                first_segment_len = source_unit_length if source_unit_length <= total_length else total_length
                loop_end_value = float(first_segment_len)

                if loop_end_value < loop_start_value:
                    raise ValueError("length_beats must be positive")

                # Order matters for Live: end first, then start
                new_arrangement_clip.loop_end = loop_end_value
                new_arrangement_clip.loop_start = loop_start_value
                # Extend the clip in Arrangement so multiple loop cycles are visible
                # end_marker is clip-local; set to desired total length
                try:
                    # Normalize markers to clip-local 0..length
                    new_arrangement_clip.start_marker = 0.0
                    new_arrangement_clip.end_marker = loop_end_value
                except Exception:
                    pass
                new_arrangement_clip.looping = desired_looping

                # If the requested total length exceeds the source unit length,
                # create additional arrangement clips to cover the remaining range
                created_count = 1
                remaining = float(total_length) - float(first_segment_len)
                while remaining > 1e-6:
                    seg_start = float(start_beats) + created_count * float(source_unit_length)
                    try:
                        extra_clip = track.duplicate_clip_to_arrangement(slot.clip, seg_start)
                    except Exception as e:
                        raise RuntimeError("Track.duplicate_clip_to_arrangement failed: {0}".format(str(e)))
                    if extra_clip is not None:
                        seg_len = float(source_unit_length) if remaining >= float(source_unit_length) else float(remaining)
                        try:
                            extra_clip.loop_end = seg_len
                            extra_clip.loop_start = 0.0
                            extra_clip.start_marker = 0.0
                            extra_clip.end_marker = seg_len
                            extra_clip.looping = desired_looping
                        except Exception:
                            pass
                        created_count += 1
                        remaining -= seg_len

                post_state = _state_dict(new_arrangement_clip)
                _log_obj("duplicate_to_arrangement post", post_state)

            # Diagnostics-only: return clip state without mutating properties
            # Try to compute a stable index of the new clip in arrangement_clips
            arrangement_clip_index = None
            try:
                clips = list(track.arrangement_clips)
                # Prefer identity match if possible
                for i, c in enumerate(clips):
                    try:
                        if c == new_arrangement_clip:
                            arrangement_clip_index = i
                            break
                    except Exception:
                        pass
                if arrangement_clip_index is None:
                    # Fallback: match by start_time
                    target_start = getattr(new_arrangement_clip, 'start_time', float(start_beats))
                    for i, c in enumerate(clips):
                        try:
                            if abs(c.start_time - float(target_start)) < 1e-6:
                                arrangement_clip_index = i
                                break
                        except Exception:
                            pass
            except Exception:
                pass

            # Build a full snapshot of arrangement clips on this track for debugging
            def _clip_state(c):
                try:
                    return {
                        "start_time": getattr(c, "start_time", None),
                        "end_time": getattr(c, "end_time", None),
                        "looping": getattr(c, "looping", None),
                        "loop_start": getattr(c, "loop_start", None),
                        "loop_end": getattr(c, "loop_end", None),
                        "start_marker": getattr(c, "start_marker", None),
                        "end_marker": getattr(c, "end_marker", None),
                        "length": getattr(c, "length", None),
                    }
                except Exception:
                    return {}

            track_snapshot = []
            try:
                for i, c in enumerate(list(track.arrangement_clips)):
                    s = _clip_state(c)
                    s["index"] = i
                    track_snapshot.append(s)
            except Exception:
                pass

            result = {
                "track_index": track_index,
                "arrangement_clip_id": getattr(new_arrangement_clip, 'id', None),
                "arrangement_clip_index": arrangement_clip_index,
                "start_time": getattr(new_arrangement_clip, 'start_time', float(start_beats)),
                "end_time": getattr(new_arrangement_clip, 'end_time', None),
                "looping": getattr(new_arrangement_clip, 'looping', None),
                "loop_start": getattr(new_arrangement_clip, 'loop_start', None),
                "loop_end": getattr(new_arrangement_clip, 'loop_end', None),
                "debug": {
                    "pre": pre_state if 'pre_state' in locals() else None,
                    "post": post_state if 'post_state' in locals() else None,
                    "track_arrangement_snapshot": track_snapshot,
                    "created_count": created_count if 'created_count' in locals() else 1,
                    "source_unit_length": source_unit_length if 'source_unit_length' in locals() else None,
                }
            }
            return result
        except Exception as e:
            self.log_message("Error duplicating clip to arrangement: " + str(e))
            raise

    def _set_device_parameter(self, track_index, device_index, value, parameter_index=None, parameter_name=None):
        """Set a parameter for a device by index or name"""
        try:
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")

            track = self._song.tracks[track_index]

            if device_index < 0 or device_index >= len(track.devices):
                raise IndexError("Device index out of range")

            device = track.devices[device_index]

            parameter_to_set = None

            if parameter_index is not None:
                if parameter_index < 0 or parameter_index >= len(device.parameters):
                    raise IndexError("Parameter index out of range")
                parameter_to_set = device.parameters[parameter_index]
            elif parameter_name is not None:
                for param in device.parameters:
                    if param.name.lower() == parameter_name.lower():
                        parameter_to_set = param
                        break
                if parameter_to_set is None:
                    raise ValueError("Parameter with name '{0}' not found".format(parameter_name))
            else:
                raise ValueError("Either parameter_index or parameter_name must be provided")

            if not parameter_to_set.is_enabled:
                raise Exception("Parameter is not enabled")

            parameter_to_set.value = value

            return {
                "track_index": track_index,
                "device_index": device_index,
                "parameter_name": parameter_to_set.name,
                "new_value": parameter_to_set.value
            }
        except Exception as e:
            self.log_message("Error setting device parameter: " + str(e))
            raise

    # Helper methods

    def _get_device_type(self, device):
        """Get the type of a device"""
        try:
            # Simple heuristic - in a real implementation you'd look at the device class
            if device.can_have_drum_pads:
                return "drum_machine"
            elif device.can_have_chains:
                return "rack"
            elif "instrument" in device.class_display_name.lower():
                return "instrument"
            elif "audio_effect" in device.class_name.lower():
                return "audio_effect"
            elif "midi_effect" in device.class_name.lower():
                return "midi_effect"
            else:
                return "unknown"
        except:
            return "unknown"

    def get_browser_tree(self, category_type="all", max_depth=2):
        """
        Get a simplified tree of browser categories, with recursion.

        Args:
            category_type: Type of categories to get ('all', 'instruments', 'sounds', etc.)
            max_depth: How many levels of subfolders to explore.

        Returns:
            Dictionary with the browser tree structure
        """
        try:
            app = self.application()
            if not app or not hasattr(app, 'browser') or app.browser is None:
                raise RuntimeError("Browser is not available in the Live application")

            browser_attrs = [attr for attr in dir(app.browser) if not attr.startswith('_')]

            result = {
                "type": category_type,
                "categories": [],
                "available_categories": browser_attrs
            }

            def process_item_recursive(item, current_depth=0):
                if not item or current_depth >= max_depth:
                    return None

                item_info = {
                    "name": item.name if hasattr(item, 'name') else "Unknown",
                    "is_folder": hasattr(item, 'children') and bool(item.children),
                    "is_device": hasattr(item, 'is_device') and item.is_device,
                    "is_loadable": hasattr(item, 'is_loadable') and item.is_loadable,
                    "uri": item.uri if hasattr(item, 'uri') else None,
                    "children": []
                }

                if item_info["is_folder"] and current_depth < max_depth - 1:
                    for child in item.children:
                        child_info = process_item_recursive(child, current_depth + 1)
                        if child_info:
                            item_info["children"].append(child_info)

                return item_info

            categories_to_process = []
            if category_type == "all":
                categories_to_process = ['instruments', 'sounds', 'drums', 'audio_effects', 'midi_effects', 'plugins']
            else:
                categories_to_process = [category_type]

            for category_name in categories_to_process:
                if hasattr(app.browser, category_name):
                    try:
                        category_root = getattr(app.browser, category_name)
                        category_tree = process_item_recursive(category_root)
                        if category_tree:
                            result["categories"].append(category_tree)
                    except Exception as e:
                        self.log_message("Error processing category " + category_name + ": " + str(e))

            self.log_message("Browser tree generated for " + category_type + " with max_depth " + str(max_depth))
            return result

        except Exception as e:
            self.log_message("Error getting browser tree: " + str(e))
            self.log_message(traceback.format_exc())
            raise

    def get_browser_items_at_path(self, path):
        """
        Get browser items at a specific path.

        Args:
            path: Path in the format "category/folder/subfolder"
                 where category is one of: instruments, sounds, drums, audio_effects, midi_effects
                 or any other available browser category

        Returns:
            Dictionary with items at the specified path
        """
        try:
            # Access the application's browser instance instead of creating a new one
            app = self.application()
            if not app:
                raise RuntimeError("Could not access Live application")

            # Check if browser is available
            if not hasattr(app, 'browser') or app.browser is None:
                raise RuntimeError("Browser is not available in the Live application")

            # Log available browser attributes to help diagnose issues
            browser_attrs = [attr for attr in dir(app.browser) if not attr.startswith('_')]
            self.log_message("Available browser attributes: {0}".format(browser_attrs))

            # Parse the path
            path_parts = path.split("/")
            if not path_parts:
                raise ValueError("Invalid path")

            # Determine the root category
            root_category = path_parts[0].lower()
            current_item = None

            # Check standard categories first
            if root_category == "instruments" and hasattr(app.browser, 'instruments'):
                current_item = app.browser.instruments
            elif root_category == "sounds" and hasattr(app.browser, 'sounds'):
                current_item = app.browser.sounds
            elif root_category == "drums" and hasattr(app.browser, 'drums'):
                current_item = app.browser.drums
            elif root_category == "audio_effects" and hasattr(app.browser, 'audio_effects'):
                current_item = app.browser.audio_effects
            elif root_category == "midi_effects" and hasattr(app.browser, 'midi_effects'):
                current_item = app.browser.midi_effects
            else:
                # Try to find the category in other browser attributes
                found = False
                for attr in browser_attrs:
                    if attr.lower() == root_category:
                        try:
                            current_item = getattr(app.browser, attr)
                            found = True
                            break
                        except Exception as e:
                            self.log_message("Error accessing browser attribute {0}: {1}".format(attr, str(e)))

                if not found:
                    # If we still haven't found the category, return available categories
                    return {
                        "path": path,
                        "error": "Unknown or unavailable category: {0}".format(root_category),
                        "available_categories": browser_attrs,
                        "items": []
                    }

            # Navigate through the path
            for i in range(1, len(path_parts)):
                part = path_parts[i]
                if not part:  # Skip empty parts
                    continue

                if not hasattr(current_item, 'children'):
                    return {
                        "path": path,
                        "error": "Item at '{0}' has no children".format('/'.join(path_parts[:i])),
                        "items": []
                    }

                found = False
                for child in current_item.children:
                    if hasattr(child, 'name') and child.name.lower() == part.lower():
                        current_item = child
                        found = True
                        break

                if not found:
                    return {
                        "path": path,
                        "error": "Path part '{0}' not found".format(part),
                        "items": []
                    }

            # Get items at the current path
            items = []
            if hasattr(current_item, 'children'):
                for child in current_item.children:
                    item_info = {
                        "name": child.name if hasattr(child, 'name') else "Unknown",
                        "is_folder": hasattr(child, 'children') and bool(child.children),
                        "is_device": hasattr(child, 'is_device') and child.is_device,
                        "is_loadable": hasattr(child, 'is_loadable') and child.is_loadable,
                        "uri": child.uri if hasattr(child, 'uri') else None
                    }
                    items.append(item_info)

            result = {
                "path": path,
                "name": current_item.name if hasattr(current_item, 'name') else "Unknown",
                "uri": current_item.uri if hasattr(current_item, 'uri') else None,
                "is_folder": hasattr(current_item, 'children') and bool(current_item.children),
                "is_device": hasattr(current_item, 'is_device') and current_item.is_device,
                "is_loadable": hasattr(current_item, 'is_loadable') and current_item.is_loadable,
                "items": items
            }

            self.log_message("Retrieved {0} items at path: {1}".format(len(items), path))
            return result

        except Exception as e:
            self.log_message("Error getting browser items at path: {0}".format(str(e)))
            self.log_message(traceback.format_exc())
            raise
