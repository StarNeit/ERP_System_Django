from django import dispatch

design_submitted = dispatch.Signal(providing_args=["instance"])
design_created = dispatch.Signal(providing_args=["instance"])
