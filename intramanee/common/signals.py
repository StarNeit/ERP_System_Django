from django import dispatch

doc_touched = dispatch.Signal(providing_args=["instance", "is_new"])
