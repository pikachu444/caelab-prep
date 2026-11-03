"""One classification of native actions for menus and presentation adapters."""


def command_groups(host):
    model = host.modeling.actions
    return {
        "Document": (host.open_rad_action, host.open_project_action, host.save_action, host.export_action),
        "History": (host.undo_action, host.redo_action),
        "Material": (host.edit_properties_action, model["material.create"]),
        "Section": (model["section.create"], model["solid_section.create"]),
        "Object": (model["object.edit"], model["object.copy"], model["object.delete"]),
        "Assignment": (model["part.assign"],),
        "Selection": tuple(model[key + ".create"] for key in
                           ("group", "element_group", "surface", "coordinate_system")),
        "Curve": (model["curve.create"],),
        "Conditions": tuple(model[key + ".create"] for key in
                            ("constraint", "load", "velocity", "contact")) + (host.mesh_workflow.cases_action,),
    }


def menu_sections(host):
    """Reuse the registered QAction instances, including their enablement/keys."""
    groups = command_groups(host)
    return (
        ("&File", ((host.mesh_workflow.new_action, host.open_rad_action, host.open_project_action),
                   (host.source_models_action,),
                   (host.save_action, host.save_as_action, host.export_action, host.mesh_workflow.export_action),
                   (host.close_action,))),
        ("&Edit", (groups["History"], (host.reload_properties_action,))),
        ("&Model", (groups["Material"], groups["Section"], groups["Selection"],
                    groups["Object"], groups["Assignment"])),
        ("&Mesh", ((host.mesh_import.action, host.mesh_workflow.mesh_action),
                   (host.node_move_action, host.node_merge_action, host.prepared_mesh_action))),
        ("&Conditions", (groups["Curve"], groups["Conditions"])),
        ("&View", ((host.fit_action, host.fit_selected_action, host.iso_action,
                    *host.standard_view_actions, host.edges_action),
                   (host.hide_selected_action, host.isolate_action, host.show_all_action))),
    )
