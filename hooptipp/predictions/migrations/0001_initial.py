from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='TipType',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100)),
                ('slug', models.SlugField(unique=True)),
                ('description', models.TextField(blank=True)),
                (
                    'category',
                    models.CharField(
                        choices=[('game', 'Spiel'), ('player', 'Spieler'), ('team', 'Team'), ('season', 'Saison')],
                        default='game',
                        max_length=20,
                    ),
                ),
                ('deadline', models.DateTimeField(help_text='Nach Ablauf dieser Zeit sind keine Tipps mehr möglich.')),
                ('is_active', models.BooleanField(default=True)),
            ],
            options={
                'verbose_name': 'Tipp-Art',
                'verbose_name_plural': 'Tipp-Arten',
                'ordering': ['deadline'],
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
                (
                    'tip_type',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='games',
                        to='predictions.tiptype',
                    ),
                ),
            ],
            options={
                'verbose_name': 'Anstehendes Spiel',
                'verbose_name_plural': 'Anstehende Spiele',
                'ordering': ['game_date'],
            },
        ),
        migrations.CreateModel(
            name='UserTip',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('prediction', models.CharField(max_length=255)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                (
                    'scheduled_game',
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='tips',
                        to='predictions.scheduledgame',
                    ),
                ),
                (
                    'tip_type',
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='predictions.tiptype'),
                ),
                (
                    'user',
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL),
                ),
            ],
            options={
                'verbose_name': 'Tipp',
                'verbose_name_plural': 'Tipps',
            },
        ),
        migrations.AlterUniqueTogether(
            name='usertip',
            unique_together={('user', 'tip_type', 'scheduled_game')},
        ),
    ]
