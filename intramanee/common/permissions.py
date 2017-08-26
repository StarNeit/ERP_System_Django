__author__ = 'peat'

permission_center = []  # Collection of tuple (name, possible permissions)


def create_user_permissions(**kwargs):
    """
    Generate user's permission array

    :param kwargs:
    :return:
    """
    r = []
    for module_name, perms in kwargs.iteritems():
        # standard value
        if perms == 'crud' or perms == 'CRUD':
            perms = ['read', 'write', 'delete']

        # really create the value
        for perm in perms:
            if ";" in perm:
                (op, args) = perm.split(";", 1)
                for a in args.split(","):
                    if len(a) > 0:
                        r.append("%s+%s@%s" % (module_name, op, a))
            else:
                r.append("+".join([module_name, perm]))
    return r


def register_module_permissions(module_name, read, write, delete):
    """
    Generate module's possible permission array

    :param module_name:
    :param read:
    :param write:
    :param delete:
    :return:
    """
    r = []
    for operator, option in {'read':read, 'write':write, 'delete': delete}.iteritems():
        base = "%s+%s" % (module_name, operator)
        if isinstance(option, (list, tuple)):
            r.extend(map(lambda v: "%s@%s" % (base, v) if v is not None else "%s" % base, option))
        elif option:
            r.append(base)
    register(r)


def register(permissions):
    permission_center.extend(permissions)
