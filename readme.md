Sublime Text 'Smart' VHDL Package
==================================


General
-----------

The goal of this plugin is to provide IDE-like features for VHDL (similar to my other plugin for SystemVerilog) :


Compare to the basic VHDL plugin it already proposes:

 * a proper symbol definition for easy code navigation
 * Some basic indentation definition
 * A complete set of snippets written by https://github.com/ccornish
 * Tooltip to get signal definition on mouse hover
 * Generate a design hierarchy (list of every sub-block) (available in the command panel)
 * Navigation side-bar:
   - Display instances/procedure/functions inside the current module/package
   - Double click on instance/type to jump to it

Future features includes code completion (for record, enum, ...), code alignement, block instantiation, ...


Description
-----------

#### Syntax Highlighting:
Syntax highlighting is based on the VHDL bundle for Textmate, with a rework of scope to be aligned with the SystemVerilog plugin and some support of VHDL2008 features

Note: the default color scheme (Monokai) is missing a lot of scope, and might not give the best results.
You can try my personal variation of Sunburst : https://bitbucket.org/Clams/sublimesystemverilog/downloads/Sunburst2.tmTheme


#### Code Navigation:

 * Show signal declaration in tooltip or status bar
 * Show hierarchy of a block (all its sub-block and their sub-block)
 * Find Instances: find all instance of a module inside a project


#### Module Instance helper:

 * Instantiation: Select a module from a list and create instantiation and connection


#### Code Alignement:

 * Align module instantiation


#### Configuration
To see all existing configuration option, go to Preferences->Package Settings->SmartVHDL->Settings (Default).

To edit settings open the Settings (User), and add parameter with the value you want.


Keymapping example
------------------

To map key to the different feature, simply add the following to your user .sublime-keymap file:

```json
	{
		"keys": ["ctrl+f10"], "command": "vhdl_module_inst",
		"context":
		[
			{ "key": "num_selections", "operator": "equal", "operand": 1 },
			{ "key": "selector", "operator": "equal", "operand": "source.vhdl"}
		]
	},
	{
		"keys": ["ctrl+shift+a"], "command": "vhdl_align",
		"context":
		[
			{ "key": "selector", "operator": "equal", "operand": "source.vhdl"}
		]
	},
	{
		"keys": ["ctrl+alt+f"], "command": "vhdl_find_instance",
		"context":
		[
			{ "key": "selector", "operator": "equal", "operand": "source.vhdl"}
		]
	},
	{
		"keys": ["f12"], "command": "vhdl_hierarchy_goto_definition",
		"context":[
			{ "key": "selector", "operator": "equal", "operand": "text.result-vhdl"}
		]
	},
	{ "keys": ["f1"], "command": "vhdl_toggle_navbar", "args":{"cmd":"toggle"}},
	{ "keys": ["ctrl+f1"], "command": "vhdl_toggle_lock_navbar"},
	{
	  "keys": ["alt+f1"], "command": "vhdl_show_navbar",
	  "context":[{ "key": "selector", "operator": "equal", "operand": "source.vhdl"}]
	}

```