class ValidationError(ValueError):
    """
    Raised a bad value is submitted.
    """

    def __init__(self, message="", *args, **kwargs):
        ValueError.__init__(self, message, *args, **kwargs)

