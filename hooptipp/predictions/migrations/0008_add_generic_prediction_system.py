# Generated migration for generic prediction system

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('predictions', '0007_remove_userpreferences_theme_primary_color_and_more'),
    ]

    operations = [
        # Create OptionCategory model
        migrations.CreateModel(
            name='OptionCategory',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('slug', models.SlugField(unique=True)),
                ('name', models.CharField(max_length=100)),
                ('description', models.TextField(blank=True)),
                ('icon', models.CharField(blank=True, help_text="Icon identifier for UI display (e.g., 'basketball', 'flag', 'check')", max_length=50)),
                ('is_active', models.BooleanField(default=True)),
                ('sort_order', models.PositiveIntegerField(default=0)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'Option category',
                'verbose_name_plural': 'Option categories',
                'ordering': ['sort_order', 'name'],
            },
        ),
        
        # Create Option model
        migrations.CreateModel(
            name='Option',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('slug', models.SlugField(max_length=100)),
                ('name', models.CharField(max_length=200)),
                ('short_name', models.CharField(blank=True, help_text="Abbreviated name (e.g., 'LAL' for Lakers, 'USA' for United States)", max_length=50)),
                ('description', models.TextField(blank=True)),
                ('metadata', models.JSONField(blank=True, default=dict, help_text='Flexible storage for category-specific data (e.g., team conference, player position)')),
                ('external_id', models.CharField(blank=True, help_text='Reference to external API/system (e.g., BallDontLie team ID)', max_length=200)),
                ('sort_order', models.PositiveIntegerField(default=0)),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('category', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='options', to='predictions.optioncategory')),
            ],
            options={
                'verbose_name': 'Option',
                'verbose_name_plural': 'Options',
                'ordering': ['category', 'sort_order', 'name'],
            },
        ),
        
        # Add indexes to Option
        migrations.AddIndex(
            model_name='option',
            index=models.Index(fields=['category', 'is_active'], name='predictions_categor_236d80_idx'),
        ),
        migrations.AddIndex(
            model_name='option',
            index=models.Index(fields=['external_id'], name='predictions_externa_18f56e_idx'),
        ),
        migrations.AlterUniqueTogether(
            name='option',
            unique_together={('category', 'slug')},
        ),
        
        # Add new fields to PredictionEvent
        migrations.AddField(
            model_name='predictionevent',
            name='metadata',
            field=models.JSONField(blank=True, default=dict, help_text='Source-specific data and additional event properties'),
        ),
        migrations.AddField(
            model_name='predictionevent',
            name='source_event_id',
            field=models.CharField(blank=True, help_text='External event ID from the source system', max_length=200),
        ),
        migrations.AddField(
            model_name='predictionevent',
            name='source_id',
            field=models.CharField(blank=True, help_text="Identifier for the EventSource that created this event (e.g., 'nba-balldontlie', 'olympics-2028')", max_length=100),
        ),
        migrations.AlterField(
            model_name='predictionevent',
            name='target_kind',
            field=models.CharField(choices=[('team', 'Team'), ('player', 'Player'), ('generic', 'Generic')], default='team', max_length=10),
        ),
        migrations.AddIndex(
            model_name='predictionevent',
            index=models.Index(fields=['source_id', 'source_event_id'], name='predictions_source__afcc43_idx'),
        ),
        migrations.AddIndex(
            model_name='predictionevent',
            index=models.Index(fields=['is_active', 'opens_at', 'deadline'], name='predictions_is_acti_655837_idx'),
        ),
        
        # Remove old PredictionOption fields and add new option field
        # First remove unique_together constraint
        migrations.AlterUniqueTogether(
            name='predictionoption',
            unique_together=set(),
        ),
        # Then remove the fields
        migrations.RemoveField(
            model_name='predictionoption',
            name='player',
        ),
        migrations.RemoveField(
            model_name='predictionoption',
            name='team',
        ),
        migrations.AddField(
            model_name='predictionoption',
            name='option',
            field=models.ForeignKey(help_text='Generic option reference for any type of prediction target', on_delete=django.db.models.deletion.CASCADE, related_name='prediction_options', to='predictions.option', null=True),
        ),
        migrations.AlterUniqueTogether(
            name='predictionoption',
            unique_together={('event', 'option')},
        ),
        
        # Add winning_generic_option to EventOutcome and remove old fields
        migrations.RemoveField(
            model_name='eventoutcome',
            name='winning_player',
        ),
        migrations.RemoveField(
            model_name='eventoutcome',
            name='winning_team',
        ),
        migrations.AddField(
            model_name='eventoutcome',
            name='winning_generic_option',
            field=models.ForeignKey(blank=True, help_text='The underlying generic Option that won (denormalized for easier querying)', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='winning_event_outcomes', to='predictions.option'),
        ),
        migrations.AlterField(
            model_name='eventoutcome',
            name='winning_option',
            field=models.ForeignKey(blank=True, help_text='The PredictionOption that won (includes label and event context)', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='winning_outcomes', to='predictions.predictionoption'),
        ),
        
        # Update UserTip fields
        # First remove unique_together constraints
        migrations.AlterUniqueTogether(
            name='usertip',
            unique_together=set(),
        ),
        # Then remove the fields
        migrations.RemoveField(
            model_name='usertip',
            name='scheduled_game',
        ),
        migrations.RemoveField(
            model_name='usertip',
            name='selected_player',
        ),
        migrations.RemoveField(
            model_name='usertip',
            name='selected_team',
        ),
        migrations.AddField(
            model_name='usertip',
            name='selected_option',
            field=models.ForeignKey(blank=True, help_text='The underlying generic option selected (denormalized for easier querying)', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='tips', to='predictions.option'),
        ),
        migrations.AlterField(
            model_name='usertip',
            name='prediction',
            field=models.CharField(help_text='Human-readable prediction text', max_length=255),
        ),
        migrations.AlterField(
            model_name='usertip',
            name='prediction_event',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='tips', to='predictions.predictionevent'),
        ),
        migrations.AlterField(
            model_name='usertip',
            name='prediction_option',
            field=models.ForeignKey(blank=True, help_text='The specific option the user selected (references a PredictionOption from the event)', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='tips', to='predictions.predictionoption'),
        ),
        migrations.AlterUniqueTogether(
            name='usertip',
            unique_together={('user', 'prediction_event')},
        ),
        migrations.AddIndex(
            model_name='usertip',
            index=models.Index(fields=['user', 'is_locked'], name='predictions_user_id_locked_idx'),
        ),
        migrations.AddIndex(
            model_name='usertip',
            index=models.Index(fields=['prediction_event', 'user'], name='predictions_event_user_idx'),
        ),
    ]
