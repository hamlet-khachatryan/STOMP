import click

_AUTO_WORDS = {"auto", "all", "none", "0"}


class MapCapType(click.ParamType):
    """
    A positive map count, or "auto" (also "all", "none", 0) which becomes None
    """

    name = "INTEGER|auto"

    def convert(self, value, param, ctx):
        if value is None:
            return None
        if str(value).strip().lower() in _AUTO_WORDS:
            return None
        try:
            cap = int(value)
        except ValueError:
            self.fail(f"{value!r} is not a whole number or 'auto'", param, ctx)
        if cap < 0:
            self.fail(f"{cap} must be positive, or 'auto'", param, ctx)
        return cap or None


MAP_CAP = MapCapType()
