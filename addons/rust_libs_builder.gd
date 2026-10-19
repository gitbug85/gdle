@tool
extends EditorPlugin

func _build() -> bool:
	print("--- Compiling Rust GDExtension... ---")
	
	# Adjust the path to where your Cargo.toml is located
	# "." assumes your Rust project is in the root Godot project folder
	var rust_project_path = ProjectSettings.globalize_path("res://libs/coords") 
	
	var output = []
	var exit_code = OS.execute(
		"cargo", 
		["build", "--manifest-path", rust_project_path + "Cargo.toml"], 
		output, 
		true # Keep true so Godot blocks until compilation is finished
	)
	
	if exit_code == 0:
		print("--- Rust Build Successful! ---")
		return true
	else:
		printerr("--- Rust Build Failed! ---")
		for line in output:
			print(line)
		return false
