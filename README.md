# README #

***Intraman*** is a Django web application project aimed to provided the ERP solution for **Intramanee**.

**Django Version**: 1.6.11 (norel variant)
**Backed Database**: MongoDB

## Install Intraman

1. To install intraman, create a project in PyCharm, 
1. Pull source code from the repository.
1. Create virtualenv for your working directory.
1. Activate your virtualenv ``source venv/bin/activate`` or ``venv\Scripts\activate.bat`` in windows.
1. Install required django-norel module first
    * ``(venv) pip install git+https://github.com/django-nonrel/django@nonrel-1.5``
    * ``(venv) pip install -r requirement.txt``
1. Sync necessary data
    * ``(venv) python manage.py syncdb``
    * ``(venv) python manage.py loaddata lov``
1. Create your first **superuser**
    * ``(venv) python manage.py shell``
        * ``>> from intramanee.common.models import IntraUser``
        * ``>> IntraUser.objects.create_superuser('code', 'firstname', 'password')``
1. Login to system with just created user.

## Development Notes

We are working on ``master`` branch. ``deployed`` is for certain deployed instance only. Only merged master to it when requested.

## Deployment

For deployment, setup ``application.wsgi``, then also collect all statics data to certain directories.

### After deployment don't forget to restart server - and - update static files.

``(venv) sudo apache2ctl restart``
``(venv) python manage.py collectstatic``

## Deployed instances

Intramanee on AWS (EC2 - Ubuntu)

* URL: intra.intramanee.com
* IP ADDRESS: 54.179.186.189
* Branch: ``deployed`` 

To access as we do not have the domain name mapped just yet, edit your ``/etc/hosts`` file. Add following content

```
54.179.186.189  intra.intramanee.com
```

## Django Utilities

1. Database Migrating - During the implementation you would always come across data update. Or data index setup. To make that happen. You can simply call:

```env/bin/python manage.py syncdb```

However to make it work; you need to import your models within ```__init__.py``` file of your based application file. If this works correctly, your database would then have the index setup properly.

1. Database Preloaded data - to make this available, the system called this ```fixtures``` - Django will always look this up in ```app/fixtures``` directory. To make this data available simply; dump it from database by calling

```env/bin/python manage.py dumpdata <app>.<module> > <dest_file>.json``` (Table name)

Now to install preloaded data - make call to

```env/bin/python manage.py loaddata <table name>```

for example:

```env/bin/python manage.py loaddata lov```