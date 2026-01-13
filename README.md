# AbletonMCP - Ableton Live Model Context Protocol Integration

AbletonMCP connects Ableton Live to Claude AI through the Model Context Protocol (MCP), allowing Cursor/Claude to directly interact with and control Ableton Live.
The goal of this (forked) integration is to comprehensively support the [Ableton Live Object Model](https://docs.cycling74.com/apiref/lom/).

## Features

- **Two-way communication**: Connect Claude AI to Ableton Live through a socket-based server
- **Track manipulation**: Create, modify, and manipulate MIDI and audio tracks
- **Instrument and effect selection**: Claude can access and load the right instruments, effects and sounds from Ableton's library
- **Clip creation**: Create and edit MIDI clips with notes
- **Session control**: Start and stop playback, fire clips, and control transport
- **Scene Management**: Create, list, fire, and rename scenes
- **Advanced Device Control**: Get and set device parameters by name, delete devices, and find devices by name.
- **Automation**: Write automation curves for device parameters.
- **Max for Live Integration**: Modify `.amxd` files by changing default parameter values.
- **Arrangement View Control**: List and create locators, and set the song position.
- **Mixer Control**: List return tracks and set send levels.
- **User Feedback**: Display messages in the Ableton Live status bar.

## Project History

This project was created by Siddharth Ahuja and has been improved. The latest updates include a host of new features that significantly expand the capabilities of AbletonMCP, including:

- Enhanced browser navigation with recursive exploration.
- Scene management.
- Advanced device control.
- Automation writing.
- Max for Live integration.
- Arrangement View control.
- Mixer control.
- Audio track creation.
- User feedback messages.

## Installation

### Prerequisites

- Ableton Live 10 or newer
- Python 3.8 or newer
- [uv package manager](https://astral.sh/uv)

If you're on Mac, please install uv as:
```
brew install uv
```

Otherwise, install from [uv's official website][https://docs.astral.sh/uv/getting-started/installation/]

⚠️ Do not proceed before installing UV

### Claude for Desktop Integration

[Follow along with the setup instructions video](https://youtu.be/iJWJqyVuPS8)

1. Go to Claude > Settings > Developer > Edit Config > claude_desktop_config.json to include the following:

```json
{
    "mcpServers": {
        "AbletonMCP": {
            "command": "uvx",
            "args": [
                "ableton-mcp"
            ]
        }
    }
}
```

### Cursor Integration

Run ableton-mcp without installing it permanently through uvx. Go to Cursor Settings > MCP and paste this as a command:

```
uvx ableton-mcp
```

⚠️ Only run one instance of the MCP server (either on Cursor or Claude Desktop), not both

### Installing the Ableton Remote Script

[Follow along with the setup instructions video](https://youtu.be/iJWJqyVuPS8)

1. Download the `AbletonMCP_Remote_Script/__init__.py` file from this repo

2. Copy the folder to Ableton's MIDI Remote Scripts directory. Different OS and versions have different locations. **One of these should work, you might have to look**:

   **For macOS:**
   - Method 1: Go to Applications > Right-click on Ableton Live app → Show Package Contents → Navigate to:
     `Contents/App-Resources/MIDI Remote Scripts/`
   - Method 2: If it's not there in the first method, use the direct path (replace XX with your version number):
     `/Users/[Username]/Library/Preferences/Ableton/Live XX/User Remote Scripts`

   **For Windows:**
   - Method 1:
     C:\Users\[Username]\AppData\Roaming\Ableton\Live x.x.x\Preferences\User Remote Scripts
   - Method 2:
     `C:\ProgramData\Ableton\Live XX\Resources\MIDI Remote Scripts\`
   - Method 3:
     `C:\Program Files\Ableton\Live XX\Resources\MIDI Remote Scripts\`
   *Note: Replace XX with your Ableton version number (e.g., 10, 11, 12)*

4. Create a folder called 'AbletonMCP' in the Remote Scripts directory and paste the downloaded '\_\_init\_\_.py' file

3. Launch Ableton Live

4. Go to Settings/Preferences → Link, Tempo & MIDI

5. In the Control Surface dropdown, select "AbletonMCP"

6. Set Input and Output to "None"

## Usage

### Starting the Connection

1. Ensure the Ableton Remote Script is loaded in Ableton Live
2. Make sure the MCP server is configured in Claude Desktop or Cursor
3. The connection should be established automatically when you interact with Claude

### Using with Claude

Once the config file has been set on Claude, and the remote script is running in Ableton, you will see a hammer icon with tools for the Ableton MCP.

### Debugger CLI

A lightweight command-line debugger is provided to quickly test server commands and prototype new ones with stubs.

Start a REPL:

```
uvx ableton-mcp-debug repl
```

Send a single command:

```
uvx ableton-mcp-debug send set_tempo '{"tempo": 120}'
```

Inside the REPL:

- `send <command_type> [JSON_PARAMS]` — send a command, pretty-print result
- `commands` — list known command names discovered from the server source
- `info` — shortcut for `send get_session_info`
- Stub controls for unimplemented commands:
  - `stub_add <command_type> <JSON_RESPONSE>`
  - `stub_remove <command_type>`
  - `stub_list`
  - `stub_clear`
  - `stub_toggle` / `stub_on` / `stub_off`

Environment:

- `ABLETON_MCP_HOST` and `ABLETON_MCP_PORT` customize the target host/port (defaults: localhost:9877)

### Running Tests

Integration tests expect Ableton Live running with the AbletonMCP Remote Script loaded and an empty project.

Run all tests:

```
uvx pytest -q
```

Only the integration suite:

```
uvx pytest -q tests/test_integration_song_creation.py
```

## Command List

### Songs & Transport
- `get_session_info()`: Get detailed information about the current Ableton session.
  - **Example**: "Get the session info."
- `set_tempo(tempo: float)`: Set the tempo of the Ableton session.
  - **Example**: "Set the tempo to 120 BPM."
- `set_signature_denominator(denom: int)` and `set_signature_numerator(numer: int)`: set the time signature of the song.
  - **Example**: "Set time signature to 7/8"
- `start_playback()`: Start playing the Ableton session.
  - **Example**: "Start playback."
- `stop_playback()`: Stop playing the Ableton session.
  - **Example**: "Stop playback."
- `continue_playing()`: Continue playback from the current position.
  - **Example**: "Continue playback."
- `jump_by(beats: float)`: Jump forwards/backwards by a number of beats.
  - **Example**: "Jump forward by 4 beats."
- `set_record_mode(on: bool)`: Enable or disable record mode.
  - **Example**: "Turn record mode on."
- `set_arrangement_overdub(on: bool)`: Toggle arrangement overdub.
  - **Example**: "Enable arrangement overdub."
- `re_enable_automation()`: Re-enable automation after manual changes.
  - **Example**: "Re-enable automation."

### Locators & Cues
- `list_locators()`: Get a list of all locators (cue points).
  - **Example**: "List all locators."
- `create_locator(time: float)`: Create a locator at a specific beat.
  - **Example**: "Create a locator at beat 32."
- `rename_cue_point(cue_index: int, name: str)`: Rename a cue by index.
  - **Example**: "Rename cue 0 to 'Verse'."
- `jump_to_next_cue()`: Jump to the next cue point.
  - **Example**: "Jump to next cue."
- `jump_to_prev_cue()`: Jump to the previous cue point.
  - **Example**: "Jump to previous cue."
- `jump_to_cue(index: int)`: Jump to a specific cue point by index.
  - **Example**: "Jump to cue 0."
- `toggle_cue_at_current()`: Toggle a cue at the current position.
  - **Example**: "Toggle cue at the current position."

### Arrangement
- `set_song_position(time: float)`: Set the current playback time in beats.
  - **Example**: "Set the song position to beat 16."
- `set_current_song_time_beats(beats: float)`: Write `Song.current_song_time` exactly in beats.
  - **Example**: "Set current song time to beat 16."
- `get_current_song_time_beats()`: Read current song time in beats and as bars.beats.sixteenths.ticks.
  - **Example**: "Read current song time in beats."
- `set_back_to_arranger(on: bool)`: Toggle Back to Arranger.
  - **Example**: "Enable Back to Arranger."
- `set_start_time(beats: float)`: Set the arrangement start marker.
  - **Example**: "Set start marker to beat 0."
- `set_metronome(on: bool)`: Turn the metronome on/off.
  - **Example**: "Turn the metronome on."
- `set_clip_trigger_quantization(quant: int)`: Set global clip trigger quantization.
  - **Example**: "Set clip quantization to 1 bar."
- `set_loop(on: bool)`: Enable or disable arrangement loop.
  - **Example**: "Enable loop."
- `set_loop_region(start: float, length: float)`: Set arrangement loop start and length.
  - **Example**: "Loop from beat 32 for 16 beats."
- `play_selection()`: Play the current selection in Arrangement.
  - **Example**: "Play selection."
- `clear_arrangement(track_indices: List[int] = None)`: Delete all arrangement clips on specified tracks (or all).
  - **Example**: "Clear arrangement on tracks 0 and 1."
- `duplicate_track_clip_to_arrangement(track_index: int, clip_index: int, start_beats: float, length_beats: float, loop: bool = false)`: Duplicate a Session clip to Arrangement using `Track.duplicate_clip_to_arrangement` at `start_beats`. The new Arrangement clip is always looped with `looping = true`, `loop_start = start_beats`, and `loop_end = start_beats + length_beats` (the `loop` argument is currently ignored). Returns: `{ track_index, arrangement_clip_id, start_time, end_time, looping, loop_start, loop_end }`.
  - **Note**: `Clip.end_time` is read-only on Arrangement clips. This call does not modify `start_marker`/`end_marker`; it sets the loop range instead via `loop_start`/`loop_end`.
  - **Reference**: `Clip.end_time` (read-only) — see [Cycling '74 LOM: Clip.end_time](https://docs.cycling74.com/apiref/lom/clip/#end_time)
  - **Example**: "Duplicate clip 1 from track 5 to beat 32 for 16 beats; returned fields include `looping`, `loop_start`, and `loop_end`."

### Tracks
- `get_track_info(track_index: int)`: Get detailed information about a specific track.
  - **Example**: "Get info for track 1."
- `create_midi_track(index: int = -1)`: Create a new MIDI track.
  - **Example**: "Create a new MIDI track."
- `create_audio_track(index: int = -1)`: Create a new audio track.
  - **Example**: "Create a new audio track."
- `set_track_name(track_index: int, name: str)`: Set the name of a track.
  - **Example**: "Rename track 1 to 'Drums'."

### Clips
- `create_clip(track_index: int, clip_index: int, length: float = 4.0)`: Create a new MIDI clip.
  - **Example**: "Create a 4-bar clip in track 1, slot 1."
- `add_notes_to_clip(track_index: int, clip_index: int, notes: List[...])`: Add MIDI notes to a clip.
  - **Example**: "Add a C4 note to the clip in track 1, slot 1."
- `set_clip_name(track_index: int, clip_index: int, name: str)`: Set the name of a clip.
  - **Example**: "Rename the clip in track 1, slot 1 to 'Intro'."
- `get_clip_info(track_index: int, clip_index: int)`: Get detailed information about a specific clip.
  - **Example**: "Get info for the clip in track 1, slot 1."
- `fire_clip(track_index: int, clip_index: int)`: Start playing a clip.
  - **Example**: "Play the clip in track 1, slot 1."
- `stop_clip(track_index: int, clip_index: int)`: Stop playing a clip.
  - **Example**: "Stop the clip in track 1, slot 1."

### Devices
- `load_instrument_or_effect(track_index: int, uri: str)`: Load an instrument, effect, or audio file by browser URI.
  - **Example**: "Load the 'Operator' synth on track 1."
- `get_device_parameters(track_index: int, device_index: int)`: Get device parameters.
  - **Example**: "Get the parameters for the first device on track 1."
- `get_device_details(track_index: int, device_index: int)`: Get device details.
  - **Example**: "Get details for the first device on track 1."
- `find_device_by_name(track_index: int, device_name: str)`: Find a device index by name.
  - **Example**: "Find the 'Operator' synth on track 1."
- `set_device_parameter(track_index: int, device_index: int, value: float, parameter_index: int = None, parameter_name: str = None)`: Set a parameter by index or name.
  - **Example**: "Set 'Filter Freq' on the first device of track 1 to 800."
- `delete_device(track_index: int, device_index: int)`: Delete a device from a track.
  - **Example**: "Delete the first device from track 1."
- `write_automation(track_index: int, clip_index: int, device_index: int, points: List[Dict[str, float]], parameter_index: int = None, parameter_name: str = None)`: Write automation points.
  - **Example**: "Create a filter sweep automation on the first device of track 1."

### Scenes
- `list_scenes()`: Get a list of all scenes.
  - **Example**: "List all scenes."
- `fire_scene(scene_index: int)`: Fire a scene.
  - **Example**: "Fire scene 1."
- `create_scene(scene_index: int = -1)`: Create a new scene.
  - **Example**: "Create a new scene."
- `rename_scene(scene_index: int, name: str)`: Rename a scene.
  - **Example**: "Rename scene 1 to 'Intro'."

### Browser & Loading
- `get_browser_tree(category_type: str = "all", max_depth: int = 2)`: Get a hierarchical tree of browser categories.
  - **Example**: "Get the browser tree for instruments, up to 3 levels deep."
- `get_browser_items_at_path(path: str)`: Get browser items at a specific path.
  - **Example**: "Get the items in the 'Drums' category."
- `load_drum_kit(track_index: int, rack_uri: str, kit_path: str)`: Load a drum rack and a specific kit.
  - **Example**: "Load the '808 Core Kit' on track 1."

### Mixer
- `list_return_tracks()`: Get a list of all return tracks.
  - **Example**: "List all return tracks."
- `set_send_level(track_index: int, send_index: int, level: float)`: Set a track's send level.
  - **Example**: "Set the first send on track 1 to 0.5."

### Max for Live
- `modify_m4l_device_default(input_filepath: str, output_filepath: str, parameter_name: str, new_default_value: float)`: Create a new .amxd with updated default.
  - **Example**: "Create 'MyReverb_Long.amxd' where 'Decay' defaults to 5.0."

### Misc & Feedback
- `show_message(message: str)`: Display a message in Ableton's status bar.
  - **Example**: "Show the message 'Hello from the AI!' in Ableton."

### Application
- `get_application_info()`: Get high-level info about the Live Application: dialog counts, CPU usage, and control surfaces.
  - Example: "Get application info."
- `get_application_process_usage()`: Get average and peak process usage.
  - Example: "Show current CPU usage."
- `get_application_version()`: Get Live version information (major, minor, bugfix, version string).
  - Example: "What Live version is running?"
- `get_application_document()`: Get a brief summary of the current Live Set via `Application.get_document()`.
  - Example: "Summarize the current set (track/scene counts)."
- `list_control_surfaces()`: List configured control surfaces.

#### Application.View
Following the LOM `Application.View` API, the MCP exposes properties and functions to control and query Live's UI. See official docs: [Application.View](https://docs.cycling74.com/apiref/lom/application_view/).

- `get_application_view_state()`: Read `browse_mode` and `focused_document_view`.
  - Example: "Show current browse mode and focused document view."
- `application_view_available_main_views()`: Get the constant list of main view names.
  - Returns items like `Browser`, `Arranger`, `Session`, `Detail`, `Detail/Clip`, `Detail/DeviceChain`.
- `application_view_focus_view(view_name: str)`: Show/focus a named view. Empty string focuses the main window view.
  - Example: `application_view_focus_view("Session")`
- `application_view_show_view(view_name: str)`: Show a named view (e.g., `Browser`).
- `application_view_hide_view(view_name: str)`: Hide a named view.
- `application_view_is_view_visible(view_name: str)`: Check if a view is visible.
- `application_view_scroll_view(direction: int, view_name: str = "", modifier_pressed: bool = False)`: Scroll a view.
  - `direction`: 0=up, 1=down, 2=left, 3=right
- `application_view_toggle_browse()`: Toggle Hot‑Swap Mode and show device chain/browser for selected device.
- `application_view_zoom_view(direction: int, view_name: str = "", modifier_pressed: bool = False)`: Zoom a view.
  - Only Arrangement and Session can be zoomed. For Session, zoom behaves like scroll.
  - Example: "List control surfaces."
- `press_current_dialog_button(index: int)`: Press a button in the current Live dialog.
  - Example: "Press 'OK' in the current dialog (index 0)."

### Mixer Control
- `list_return_tracks()`: Get a list of all return tracks in the Ableton session.
  - **Example**: "List all return tracks."
- `set_send_level(track_index: int, send_index: int, level: float)`: Set the send level for a track.
  - **Example**: "Set the first send on track 1 to 0.5."

### User Feedback
- `show_message(message: str)`: Display a message in Ableton's status bar.
  - **Example**: "Show the message 'Hello from the AI!' in Ableton."



## Troubleshooting

- **Connection issues**: Make sure the Ableton Remote Script is loaded, and the MCP server is configured on Claude
- **Timeout errors**: Try simplifying your requests or breaking them into smaller steps
- **Have you tried turning it off and on again?**: If you're still having connection errors, try restarting both Claude and Ableton Live

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## References
- [Unofficial Live API documentation](https://structure-void.com/ableton-live-midi-remote-scripts/)
- [Live 12.0.1 MIDI Remote Python Scripts Sources uncompiled](https://github.com/gluon/AbletonLive12_MIDIRemoteScripts/tree/main)

## Disclaimer

This is a third-party integration and not made by Ableton.
