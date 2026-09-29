class LocationNotFound(Exception):
    pass


class LocationOutsideUSA(Exception):
    pass


class RoutingUnavailable(Exception):
    pass


class RouteNotFound(Exception):
    pass


class UnreachableRoute(Exception):
    pass


class SameStartAndFinish(Exception):
    pass
