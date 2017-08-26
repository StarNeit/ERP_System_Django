__author__ = 'peat'


def menu_item(active_item):
    def wrap(f):
        def request_wrap(request, *args, **kwargs):
            r = f(request, *args, **kwargs)
            if r is not None:
                if not hasattr(r, 'context_data') or r.context_data is None:
                    r.context_data = {}
                r.context_data['active_menu'] = active_item
            return r
        return request_wrap
    return wrap


def inject_data(**callable_data):
    def wrap(f):
        def request_wrap(request, *args, **kwargs):
            r = f(request, *args, **kwargs)
            if r is not None:
                for name in callable_data:
                    print name, callable_data[name]
                    if hasattr(callable_data[name], '__call__'):
                        r.context_data[name] = callable_data[name]()
                    else:
                        r.context_data[name] = callable_data[name]
            return r
        return request_wrap
    return wrap
