"""Management command to sync DBB team options."""

from django.core.management.base import BaseCommand

from hooptipp.dbb.event_source import DbbEventSource


class Command(BaseCommand):
    """Sync DBB team options including logos."""

    help = 'Sync DBB team options (including logos) from TrackedTeams to Options'

    def handle(self, *args, **options):
        """Execute the command."""
        self.stdout.write('Syncing DBB team options...\n')
        
        event_source = DbbEventSource()
        
        if not event_source.is_configured():
            self.stdout.write(
                self.style.ERROR('DBB source is not configured (missing SLAPI_API_TOKEN)')
            )
            return
        
        result = event_source.sync_options()
        
        # Display results
        if result.options_created > 0:
            self.stdout.write(
                self.style.SUCCESS(f'Created {result.options_created} new option(s)')
            )
        
        if result.options_updated > 0:
            self.stdout.write(
                self.style.SUCCESS(f'Updated {result.options_updated} option(s)')
            )
        
        if result.errors:
            for error in result.errors:
                self.stdout.write(self.style.ERROR(f'Error: {error}'))
        
        if result.options_created == 0 and result.options_updated == 0 and not result.errors:
            self.stdout.write(self.style.WARNING('No options created or updated'))
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f'\nCompleted: {result.options_created} created, '
                    f'{result.options_updated} updated, {len(result.errors)} errors'
                )
            )

