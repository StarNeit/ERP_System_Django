from django import dispatch

task_confirmed = dispatch.Signal(providing_args=["instance", "code", "confirmation"])
task_reverted = dispatch.Signal(providing_args=["instance", "reverted_content"])
task_released = dispatch.Signal(providing_args=[])
task_repeat = dispatch.Signal(providing_args=["parent", "components"])
