class MaxTurnsExceeded(Exception):
    pass


class AntiSpinTerminated(Exception):
    pass


class ToolPermissionError(Exception):
    pass


class ToolTimeout(Exception):
    pass


class RunTimeout(Exception):
    pass
