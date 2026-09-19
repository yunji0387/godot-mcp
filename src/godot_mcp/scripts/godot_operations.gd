extends SceneTree

func _init() -> void:
    var args := OS.get_cmdline_args()
    var script_index := args.find("--script")
    if script_index < 0 or args.size() <= script_index + 3:
        printerr("Usage: godot --headless --script godot_operations.gd <operation> <json_params>")
        quit(1)
        return
    var operation: String = args[script_index + 2]
    var parsed = JSON.parse_string(args[script_index + 3])
    if not parsed is Dictionary:
        printerr("Operation parameters must be a JSON object")
        quit(1)
        return
    var ok := false
    match operation:
        "create_scene": ok = create_scene(parsed)
        "add_node": ok = add_node(parsed)
        "load_sprite": ok = load_sprite(parsed)
        "export_mesh_library": ok = export_mesh_library(parsed)
        "save_scene": ok = save_scene(parsed)
        "get_uid": ok = get_uid(parsed)
        "resave_resources": ok = resave_resources(parsed)
        _: printerr("Unknown operation: " + operation)
    quit(0 if ok else 1)

func resource_path(value: String) -> String:
    return value if value.begins_with("res://") else "res://" + value

func create_scene(params: Dictionary) -> bool:
    var path := resource_path(params["scenePath"])
    var root_type: String = params.get("rootNodeType", "Node2D")
    var root = ClassDB.instantiate(root_type)
    if root == null or not root is Node:
        printerr("Unable to instantiate root node: " + root_type)
        return false
    root.name = "root"
    var packed := PackedScene.new()
    if packed.pack(root) != OK:
        printerr("Failed to pack scene")
        return false
    var error := ResourceSaver.save(packed, path)
    if error != OK:
        printerr("Failed to save scene: " + str(error))
        return false
    print("Scene created successfully at: " + params["scenePath"])
    return true

func load_scene_root(path: String):
    var scene = load(resource_path(path))
    if scene == null:
        printerr("Failed to load scene: " + path)
        return null
    return scene.instantiate()

func add_node(params: Dictionary) -> bool:
    var root = load_scene_root(params["scenePath"])
    if root == null:
        return false
    var parent = root
    var parent_path: String = params.get("parentNodePath", "root")
    if parent_path != "root":
        parent = root.get_node_or_null(parent_path.trim_prefix("root/"))
    if parent == null:
        printerr("Parent node not found: " + parent_path)
        return false
    var node = ClassDB.instantiate(params["nodeType"])
    if node == null or not node is Node:
        printerr("Unable to instantiate node: " + params["nodeType"])
        return false
    node.name = params["nodeName"]
    for property in params.get("properties", {}):
        var value = params["properties"][property]
        if value is String and value.begins_with("res://"):
            value = load(value)
        node.set(property, value)
    parent.add_child(node)
    node.owner = root
    return pack_and_save(root, params["scenePath"])

func load_sprite(params: Dictionary) -> bool:
    var root = load_scene_root(params["scenePath"])
    if root == null:
        return false
    var node_path: String = params["nodePath"].trim_prefix("root/")
    var node = root if node_path.is_empty() else root.get_node_or_null(node_path)
    var texture = load(resource_path(params["texturePath"]))
    if node == null or texture == null or not (node is Sprite2D or node is Sprite3D or node is TextureRect):
        printerr("Invalid sprite node or texture")
        return false
    node.texture = texture
    return pack_and_save(root, params["scenePath"])

func pack_and_save(root: Node, path: String) -> bool:
    var packed := PackedScene.new()
    if packed.pack(root) != OK:
        printerr("Failed to pack scene")
        return false
    var error := ResourceSaver.save(packed, resource_path(path))
    if error != OK:
        printerr("Failed to save scene: " + str(error))
        return false
    return true

func save_scene(params: Dictionary) -> bool:
    var root = load_scene_root(params["scenePath"])
    if root == null:
        return false
    return pack_and_save(root, params.get("newPath", params["scenePath"]))

func export_mesh_library(params: Dictionary) -> bool:
    var root = load_scene_root(params["scenePath"])
    if root == null:
        return false
    var library := MeshLibrary.new()
    var selected: Array = params.get("meshItemNames", [])
    var item_id := 0
    for child in root.get_children():
        if not selected.is_empty() and not child.name in selected:
            continue
        var mesh_instance: MeshInstance3D = child as MeshInstance3D
        if mesh_instance == null:
            for descendant in child.get_children():
                if descendant is MeshInstance3D:
                    mesh_instance = descendant
                    break
        if mesh_instance != null and mesh_instance.mesh != null:
            library.create_item(item_id)
            library.set_item_name(item_id, child.name)
            library.set_item_mesh(item_id, mesh_instance.mesh)
            item_id += 1
    if item_id == 0:
        printerr("No valid meshes found in the scene")
        return false
    var output_path := resource_path(params["outputPath"])
    DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(output_path.get_base_dir()))
    return ResourceSaver.save(library, output_path) == OK

func get_uid(params: Dictionary) -> bool:
    var path := resource_path(params["filePath"])
    var uid_file := FileAccess.open(path + ".uid", FileAccess.READ)
    var result := {"file": path, "exists": uid_file != null}
    if uid_file != null:
        result["uid"] = uid_file.get_as_text().strip_edges()
        uid_file.close()
    print(JSON.stringify(result))
    return true

func resave_resources(params: Dictionary) -> bool:
    var root := resource_path(params.get("projectPath", ""))
    var scenes := find_files(root, ".tscn")
    for path in scenes:
        var scene = load(path)
        if scene != null:
            ResourceSaver.save(scene, path)
    for extension in [".gd", ".shader", ".gdshader"]:
        for path in find_files(root, extension):
            var resource = load(path)
            if resource != null:
                ResourceSaver.save(resource, path)
    print("Resave operation complete")
    return true

func find_files(path: String, extension: String) -> Array[String]:
    var result: Array[String] = []
    var directory := DirAccess.open(path)
    if directory == null:
        return result
    directory.list_dir_begin()
    var name := directory.get_next()
    while name != "":
        if name.begins_with("."):
            name = directory.get_next()
            continue
        var child_path := path.path_join(name)
        if directory.current_is_dir():
            result.append_array(find_files(child_path, extension))
        elif name.ends_with(extension):
            result.append(child_path)
        name = directory.get_next()
    directory.list_dir_end()
    return result
