import time

from django.core.management.base import BaseCommand

from apps.video_editor.services.jobs import run_next_job


class Command(BaseCommand):
    help = 'Run the local Video Editor background worker.'

    def add_arguments(self, parser):
        parser.add_argument('--poll-interval', type=float, default=2.0)
        parser.add_argument('--once', action='store_true', help='Process at most one queued job and exit.')

    def handle(self, *args, **options):
        interval = max(0.25, options['poll_interval'])
        self.stdout.write(self.style.SUCCESS('Video worker started. Press Ctrl+C to stop.'))
        try:
            while True:
                processed = run_next_job()
                if options['once']:
                    break
                if not processed:
                    time.sleep(interval)
        except KeyboardInterrupt:
            self.stdout.write('\nVideo worker stopped.')
