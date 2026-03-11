"""
Тест интеграции с OddsPapi (запускается из корня проекта)
"""

import asyncio
import os
import sys
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Добавить src в путь
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from providers.oddspapi import OddspapiProvider
from rich.console import Console
from rich.table import Table

load_dotenv()
console = Console()


async def main():
    api_key = os.getenv("ODDSPAPI_API_KEY")
    
    if not api_key:
        console.print("[red]❌ ODDSPAPI_API_KEY not found in .env[/red]")
        return
    
    console.print(f"\n[bold cyan]🎯 CS Betting Helper - OddsPapi Integration Test[/bold cyan]\n")
    console.print(f"[dim]API Key: {api_key[:20]}...[/dim]\n")
    
    async with OddspapiProvider(api_key) as provider:
        
        # Тест 1: Получить матчи
        console.rule("[yellow]Test 1: Fetch CS2 Matches[/yellow]")
        
        matches = await provider.fetch_matches(
            sport="cs2",
            from_date=datetime.now(),
            to_date=datetime.now() + timedelta(days=7),
            has_odds=True
        )
        
        console.print(f"[green]✅ Found {len(matches)} matches with odds[/green]\n")
        
        if not matches:
            console.print("[yellow]No matches found. Try increasing date range.[/yellow]")
            return
        
        # Показать таблицу матчей
        table = Table(title="Upcoming CS2 Matches")
        table.add_column("#", style="dim", width=3)
        table.add_column("Teams", style="cyan")
        table.add_column("Tournament", style="magenta")
        table.add_column("Start Time", style="green")
        
        for i, match in enumerate(matches[:15], 1):
            table.add_row(
                str(i),
                f"{match.team1.name} vs {match.team2.name}",
                match.tournament[:40],
                match.start_time.strftime("%Y-%m-%d %H:%M")
            )
        
        console.print(table)
        
        # Тест 2: Получить коэффициенты для первого матча
        console.print(f"\n")
        console.rule(f"[yellow]Test 2: Fetch Odds for Match #{1}[/yellow]")
        
        first_match = matches[0]
        console.print(f"[cyan]Match: {first_match.team1.name} vs {first_match.team2.name}[/cyan]")
        console.print(f"[dim]Tournament: {first_match.tournament}[/dim]")
        console.print(f"[dim]ID: {first_match.id}[/dim]\n")
        
        match_with_odds = await provider.fetch_match_odds(first_match.id)
        
        if not match_with_odds or not match_with_odds.bookmaker_odds:
            console.print("[red]❌ No odds available for this match[/red]")
            return
        
        console.print(f"[green]✅ Found odds from {len(match_with_odds.bookmaker_odds)} bookmakers[/green]\n")
        
        # Таблица коэффициентов
        odds_table = Table(title="Odds Comparison")
        odds_table.add_column("Bookmaker", style="yellow", width=15)
        odds_table.add_column(match_with_odds.team1.name[:20], style="cyan", justify="right")
        odds_table.add_column(match_with_odds.team2.name[:20], style="magenta", justify="right")
        odds_table.add_column("Margin %", style="dim", justify="right")
        
        for bk_odds in match_with_odds.bookmaker_odds:
            # Расчёт маржи букмекера
            implied_prob_1 = 1 / bk_odds.odds.team1_win
            implied_prob_2 = 1 / bk_odds.odds.team2_win
            margin = (implied_prob_1 + implied_prob_2 - 1) * 100
            
            odds_table.add_row(
                bk_odds.bookmaker,
                f"{bk_odds.odds.team1_win:.3f}",
                f"{bk_odds.odds.team2_win:.3f}",
                f"{margin:.2f}%"
            )
        
        console.print(odds_table)
        
        # Лучшие коэффициенты
        console.print("\n[bold]🎯 Best Odds:[/bold]")
        
        if match_with_odds.best_odds_team1:
            console.print(f"  [green]{match_with_odds.team1.name}: "
                         f"{match_with_odds.best_odds_team1.odds.team1_win:.3f} "
                         f"@ {match_with_odds.best_odds_team1.bookmaker}[/green]")
        
        if match_with_odds.best_odds_team2:
            console.print(f"  [green]{match_with_odds.team2.name}: "
                         f"{match_with_odds.best_odds_team2.odds.team2_win:.3f} "
                         f"@ {match_with_odds.best_odds_team2.bookmaker}[/green]")
        
        # Тест 3: Простая детекция арбитража
        console.print(f"\n")
        console.rule("[yellow]Test 3: Check for Arbitrage Opportunities[/yellow]")
        
        best_t1 = match_with_odds.best_odds_team1
        best_t2 = match_with_odds.best_odds_team2
        
        if best_t1 and best_t2:
            # Формула арбитража: 1/odds1 + 1/odds2 < 1
            arb_sum = (1 / best_t1.odds.team1_win) + (1 / best_t2.odds.team2_win)
            
            if arb_sum < 1:
                profit = ((1 / arb_sum) - 1) * 100
                console.print(f"[bold green]💰 ARBITRAGE FOUND! Profit: {profit:.2f}%[/bold green]")
                console.print(f"  {match_with_odds.team1.name} @ {best_t1.odds.team1_win:.3f} ({best_t1.bookmaker})")
                console.print(f"  {match_with_odds.team2.name} @ {best_t2.odds.team2_win:.3f} ({best_t2.bookmaker})")
            else:
                margin = (arb_sum - 1) * 100
                console.print(f"[yellow]No arbitrage. Combined margin: {margin:.2f}%[/yellow]")
        
        console.print("\n[bold green]✅ All tests completed successfully![/bold green]\n")


if __name__ == "__main__":
    asyncio.run(main())
