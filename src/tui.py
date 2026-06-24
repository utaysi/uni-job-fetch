"""Interactive menu for the job fetcher (rich + questionary).

Launched when jobs.py is run with no arguments. Wraps the same operations as the
CLI subcommands, with a styled status overview and confirmations.
"""

import questionary
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

import exporter
import jobs
import server
import store

console = Console()


def _status_panel():
    conn = store.connect()
    try:
        s = store.stats(conn)
    finally:
        conn.close()
    table = Table.grid(padding=(0, 2))
    table.add_column(justify='right', style='bold')
    table.add_column()
    table.add_row('Total ads', str(s['total']))
    table.add_row('Online', f"[green]{s['online']}[/green]")
    table.add_row('Offline', f"[dim]{s['offline']}[/dim]")
    table.add_row('Needs review', f"[yellow]{s['needs_review']}[/yellow]")
    return Panel(table, title='Job Repository', border_style='blue', expand=False)


class _Args:
    overwrite = False


def _do_fetch():
    console.rule('[bold]Fetch')
    jobs.cmd_fetch(_Args())


def _do_export():
    console.rule('[bold]Export to Excel')
    args = _Args()
    import os
    if os.path.exists(exporter.EXCEL_FILE):
        overwrite = questionary.confirm(
            f'{exporter.EXCEL_FILE} exists. Overwrite it? '
            '(Make sure you imported any edits first.)', default=False).ask()
        if not overwrite:
            console.print('[yellow]Export cancelled.[/yellow]')
            return
        args.overwrite = True
    jobs.cmd_export_excel(args)


def _do_import():
    console.rule('[bold]Import Excel corrections')
    jobs.cmd_import_excel(_Args())


def _do_serve():
    console.rule('[bold]Dashboard')
    console.print('Starting server. Press Ctrl+C to return to the menu.')
    try:
        server.serve()
    except KeyboardInterrupt:
        pass


ACTIONS = [
    ('Fetch new ads', _do_fetch),
    ('Export to Excel', _do_export),
    ('Import Excel corrections', _do_import),
    ('Serve dashboard', _do_serve),
    ('Quit', None),
]


def run():
    console.print('[bold cyan]Uni Marburg Job Fetcher[/bold cyan]')
    while True:
        console.print(_status_panel())
        choice = questionary.select(
            'What would you like to do?',
            choices=[label for label, _ in ACTIONS]).ask()
        if choice is None or choice == 'Quit':
            console.print('Bye.')
            return 0
        action = dict(ACTIONS)[choice]
        try:
            action()
        except Exception as e:
            console.print(f'[red]Error: {e}[/red]')
        console.print()
    return 0
