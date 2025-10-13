from .handling_ph_mark import set_markers as set_markers_ph_mark, remove_markers as remove_markers_ph_mark
from .handling_named_entitiy_id import set_markers as set_markers_neid, remove_markers as remove_markers_neid

def set_markers(text, method):
    if method == "ph_mark":
        text_marked, maps = set_markers_ph_mark(text)
        markers_information = {"maps": maps}
    elif method == "named_entitiy_id":
        text_marked, mapping = set_markers_neid(text)
        markers_information = {"mapping": mapping}
    else:
        text_marked = text
        markers_information = {}

    return text_marked, markers_information

def unset_markers(text_marked, method, markers_information):
    if method == "ph_mark":
        text = remove_markers_ph_mark(text_marked, markers_information["maps"])
    elif method == "named_entitiy_id":
        text = remove_markers_neid(text_marked, markers_information["mapping"])
    else:
        text = text_marked
    return text

__all__ = ["set_markers", "unset_markers"]