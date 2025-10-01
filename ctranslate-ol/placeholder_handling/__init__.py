from .handling_ph_mark import set_markers as set_markers_ph_mark, remove_markers as remove_markers_ph_mark

def set_markers(text, method):
    if method == "ph_mark":
        text_marked, maps = set_markers_ph_mark(text)
        markers_information = {"maps": maps}
    else:
        text_marked = text
        markers_information = {}

    return text_marked, markers_information

def unset_markers(text_marked, method, markers_information):
    if method == "ph_mark":
        text = remove_markers_ph_mark(text_marked, markers_information["maps"])
    else:
        text = text_marked
    return text

__all__ = ["set_markers", "unset_markers"]