# Generated migration to update scheduled_game foreign key to point to nba app

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('predictions', '0001_initial'),
        ('nba', '0002_nbateam_nbaplayer_scheduledgame'),
    ]

    operations = [
        migrations.AlterField(
            model_name='predictionevent',
            name='scheduled_game',
            field=models.OneToOneField(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='prediction_event',
                to='nba.scheduledgame'
            ),
        ),
    ]
