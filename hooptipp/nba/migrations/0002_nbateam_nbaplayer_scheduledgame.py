# Generated migration to move NBA models from predictions to nba app

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('nba', '0001_initial'),
        ('predictions', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='NbaTeam',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('balldontlie_id', models.PositiveIntegerField(blank=True, null=True, unique=True)),
                ('name', models.CharField(max_length=150)),
                ('abbreviation', models.CharField(blank=True, max_length=5)),
                ('city', models.CharField(blank=True, max_length=100)),
                ('conference', models.CharField(blank=True, max_length=30)),
                ('division', models.CharField(blank=True, max_length=30)),
            ],
            options={
                'ordering': ['name'],
            },
        ),
        migrations.CreateModel(
            name='NbaPlayer',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('balldontlie_id', models.PositiveIntegerField(blank=True, null=True, unique=True)),
                ('first_name', models.CharField(max_length=80)),
                ('last_name', models.CharField(max_length=80)),
                ('display_name', models.CharField(max_length=160)),
                ('position', models.CharField(blank=True, max_length=10)),
                ('team', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='players', to='nba.nbateam')),
            ],
            options={
                'ordering': ['display_name'],
            },
        ),
        migrations.CreateModel(
            name='ScheduledGame',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nba_game_id', models.CharField(max_length=20, unique=True)),
                ('game_date', models.DateTimeField()),
                ('home_team', models.CharField(max_length=100)),
                ('home_team_tricode', models.CharField(max_length=5)),
                ('away_team', models.CharField(max_length=100)),
                ('away_team_tricode', models.CharField(max_length=5)),
                ('venue', models.CharField(blank=True, max_length=150)),
                ('is_manual', models.BooleanField(default=False, help_text='Indicates that the game was added manually rather than via the BallDontLie sync.')),
                ('tip_type', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='nba_games', to='predictions.tiptype')),
            ],
            options={
                'verbose_name': 'Scheduled game',
                'verbose_name_plural': 'Scheduled games',
                'ordering': ['game_date'],
            },
        ),
    ]
