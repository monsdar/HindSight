"""
Management command to test email configuration and send a test email.

This command helps debug email configuration issues by testing the connection
and optionally sending a test email.
"""

from django.conf import settings
from django.core.mail import send_mail, get_connection
from django.core.management.base import BaseCommand, CommandError
from django.core.mail.backends.smtp import EmailBackend


class Command(BaseCommand):
    help = 'Test email configuration and optionally send a test email'

    def add_arguments(self, parser):
        parser.add_argument(
            '--to',
            type=str,
            help='Email address to send test email to (optional)',
        )
        parser.add_argument(
            '--check-only',
            action='store_true',
            help='Only check configuration without sending email',
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('Testing email configuration...\n'))
        
        # Display current email configuration
        self.stdout.write('Email Backend: {}'.format(settings.EMAIL_BACKEND))
        
        if settings.EMAIL_BACKEND == 'django.core.mail.backends.smtp.EmailBackend':
            self._test_smtp_configuration(options)
        elif settings.EMAIL_BACKEND == 'django_ses.SESBackend':
            self._test_ses_configuration()
        else:
            self.stdout.write(self.style.WARNING(
                'Using {} backend - email will be printed to console/logs'.format(
                    settings.EMAIL_BACKEND
                )
            ))
            if options['to']:
                self._send_test_email(options['to'])

    def _test_smtp_configuration(self, options):
        """Test SMTP configuration."""
        self.stdout.write('\nSMTP Configuration:')
        self.stdout.write('  Host: {}'.format(getattr(settings, 'EMAIL_HOST', 'Not set')))
        self.stdout.write('  Port: {}'.format(getattr(settings, 'EMAIL_PORT', 'Not set')))
        self.stdout.write('  Use TLS: {}'.format(getattr(settings, 'EMAIL_USE_TLS', False)))
        self.stdout.write('  Use SSL: {}'.format(getattr(settings, 'EMAIL_USE_SSL', False)))
        self.stdout.write('  Timeout: {}'.format(getattr(settings, 'EMAIL_TIMEOUT', 'Not set')))
        self.stdout.write('  User: {}'.format(getattr(settings, 'EMAIL_HOST_USER', 'Not set')))
        self.stdout.write('  From: {}'.format(getattr(settings, 'DEFAULT_FROM_EMAIL', 'Not set')))
        
        if options['check_only']:
            self.stdout.write(self.style.WARNING('\n--check-only specified, skipping connection test'))
            return
        
        # Try to open connection
        self.stdout.write('\nTesting SMTP connection...')
        try:
            connection = get_connection()
            connection.open()
            self.stdout.write(self.style.SUCCESS('✓ SMTP connection successful!'))
            connection.close()
        except Exception as e:
            self.stdout.write(self.style.ERROR('✗ SMTP connection failed!'))
            self.stdout.write(self.style.ERROR('  Error: {}'.format(str(e))))
            self.stdout.write('\nTroubleshooting tips:')
            self.stdout.write('  - Check EMAIL_HOST is correct (e.g., email-smtp.us-east-1.amazonaws.com)')
            self.stdout.write('  - Check EMAIL_PORT (587 for STARTTLS, 465 for SSL)')
            self.stdout.write('  - For port 587: EMAIL_USE_TLS=True, EMAIL_USE_SSL=False')
            self.stdout.write('  - For port 465: EMAIL_USE_SSL=True, EMAIL_USE_TLS=False')
            self.stdout.write('  - Verify EMAIL_HOST_USER and EMAIL_HOST_PASSWORD are correct')
            self.stdout.write('  - Check network/firewall allows outbound connections')
            raise CommandError('SMTP connection test failed')
        
        # Send test email if requested
        if options['to']:
            self._send_test_email(options['to'])

    def _test_ses_configuration(self):
        """Test AWS SES configuration."""
        self.stdout.write('\nAWS SES Configuration:')
        self.stdout.write('  Region: {}'.format(getattr(settings, 'AWS_SES_REGION_NAME', 'Not set')))
        self.stdout.write('  From: {}'.format(getattr(settings, 'DEFAULT_FROM_EMAIL', 'Not set')))
        
        # Note: We can't easily test SES connection without sending an email
        self.stdout.write(self.style.WARNING(
            '\nAWS SES connection will be tested when sending an email.'
        ))

    def _send_test_email(self, to_email):
        """Send a test email."""
        self.stdout.write('\nSending test email to {}...'.format(to_email))
        try:
            send_mail(
                subject='Test Email from {}'.format(getattr(settings, 'PAGE_TITLE', 'HindSight')),
                message='This is a test email to verify your email configuration is working correctly.',
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[to_email],
                fail_silently=False,
            )
            self.stdout.write(self.style.SUCCESS('✓ Test email sent successfully!'))
        except Exception as e:
            error_str = str(e)
            self.stdout.write(self.style.ERROR('✗ Failed to send test email!'))
            self.stdout.write(self.style.ERROR('  Error: {}'.format(error_str)))
            
            # Check for AWS SES Sandbox mode error
            if 'not verified' in error_str.lower() or 'sandbox' in error_str.lower():
                self.stdout.write('\n' + self.style.WARNING('⚠ AWS SES Sandbox Mode Detected'))
                self.stdout.write('\nYour AWS SES account is in Sandbox mode. In Sandbox mode, you can only send emails to verified email addresses.')
                self.stdout.write('\nTo fix this, you have two options:')
                self.stdout.write('\n1. Verify the recipient email address:')
                self.stdout.write('   - Go to AWS SES Console → Verified identities')
                self.stdout.write('   - Click "Create identity" → Email address')
                self.stdout.write('   - Enter: {}'.format(to_email))
                self.stdout.write('   - Check your inbox and click the verification link')
                self.stdout.write('\n2. Request production access (recommended for production):')
                self.stdout.write('   - Go to AWS SES Console → Account dashboard')
                self.stdout.write('   - Click "Request production access"')
                self.stdout.write('   - Fill out the form (usually approved within 24 hours)')
                self.stdout.write('   - Once approved, you can send to any email address')
            
            raise CommandError('Failed to send test email')

