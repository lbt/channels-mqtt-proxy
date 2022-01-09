This is the tutorial code from
https://channels.readthedocs.io/en/stable/tutorial/index.html up to
part 3.

It has been extended as per the main README.

Set up a venv and (as of 9/1/2022) use:

    pip install asgiref==3.3.4 Django==3.1.3 channels channels_redis


Then edit settings.py to point to your mqtt server run;

```python
python manage.py migrate
python3 manage.py runworker mqtt &
python3 manage.py runserver
```

The specific versions are needed because right now there are some
issues with Channels workers and asgiref and I've not tested Django 4
yet.

https://github.com/django/channels/issues/1713
