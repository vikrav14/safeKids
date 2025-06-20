# Generated by Django 5.2.3 on 2025-06-16 17:27

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api_app_app', '0006_add_is_active_to_child'),
    ]

    operations = [
        migrations.AlterField(
            model_name='alert',
            name='alert_type',
            field=models.CharField(choices=[('SOS', 'SOS Panic'), ('LEFT_ZONE', 'Left Safe Zone'), ('ENTERED_ZONE', 'Entered Safe Zone'), ('LOW_BATTERY', 'Low Battery'), ('UNUSUAL_ROUTE', 'Unusual Route Detected'), ('CONTEXTUAL_WEATHER', 'Contextual Weather Alert')], max_length=20),
        ),
    ]
