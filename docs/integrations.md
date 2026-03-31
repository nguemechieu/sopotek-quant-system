# Integrations

## Telegram

Telegram integration is implemented in `src/integrations/telegram_service.py` and wired through `AppController` and desktop settings.

### Settings Fields
- Telegram enabled
- Telegram bot token
- Telegram chat ID

### Automatic Notifications
Trade activity notifications can include:

- symbol
- side
- status
- price
- size
- PnL
- order ID
- timestamp

### Telegram Keyboard And Commands
The bot now supports a persistent section-based keyboard, inline menu cards, and typed commands.

Keyboard sections include:
- `Overview`
- `Portfolio`
- `Market Intel`
- `Performance`
- `Workspace`
- `Controls`
- `Journal`
- `Screenshot`
- `Help`
- `Quick Brief`

Core commands remain available for compatibility:
- `/menu`
- `/portfolio`
- `/markets`
- `/workspace`
- `/controls`
- `/status`
- `/balances`
- `/positions`
- `/orders`
- `/recommendations`
- `/performance`
- `/analysis`
- `/screenshot`
- `/chart SYMBOL [TIMEFRAME]`
- `/chartshot SYMBOL [TIMEFRAME]`
- `/ask <question>`
- `/chat <question>`

Remote trading state changes from Telegram stay confirmation-gated through inline callbacks.

### Conversational Reply Behavior
Telegram is no longer limited to slash-command prompts. Plain text messages can also be forwarded to the OpenAI-backed app context flow, which means the bot can answer natural questions about:

- account state
- balances
- positions
- performance
- recommendations
- app status
- market context

### Runtime Translation
Language changes now reach:

- visible dashboard and terminal labels
- translated runtime table and tree content
- rich-text detail panes rendered in the workspace
- dynamic Telegram summaries and remote console responses

## OpenAI

OpenAI settings are stored through the desktop settings dialog.

### Settings Fields
- OpenAI API key
- OpenAI model

### Current Use Cases
- answer questions about the app runtime context
- answer market or app workflow questions from Sopotek Pilot or Telegram
- provide chat assistance for balance, performance, recommendations, and behavior guard state
- power OpenAI speech output in Sopotek Pilot when selected
- summarize news, trade history, journal state, and recommendation reasoning from live app context

## Voice

Voice support is split between recognition and speech output.

### Recognition Providers
- `Windows`
- `Google` when the optional packages are installed

### Speech Output Providers
- `Windows`
- `OpenAI`

### Sopotek Pilot Voice Features
- listen from microphone
- speak latest reply
- auto-speak new replies
- select recognition provider and output provider independently
- choose an installed Windows voice or an OpenAI voice depending on provider

## Sopotek Pilot Command Scope

Sopotek Pilot is not only a Q&A widget. Repo evidence shows direct command handling for:

- AI trading start and stop
- AI scope changes
- kill switch and resume
- opening app windows
- screenshots
- Telegram control
- trade, cancel, and close actions with confirmation
- position analysis and trade-history review

## News

News integration is implemented through `src/integrations/news_service.py`.

Repo evidence supports:
- configurable news enabled/disabled state
- optional trade-from-news bias handling
- chart news overlays and event labels
- Sopotek Pilot use of recent news context when asked about symbol news

## Screenshot Flow

The desktop app can:
- capture full terminal screenshots
- capture chart screenshots for Telegram
- use screenshots from Sopotek Pilot or Telegram command workflows

## Security Guidance

- Treat Telegram bot tokens and OpenAI API keys as secrets.
- Prefer testing integrations on paper or practice sessions first.
- Confirm Telegram chat ID and notification routing before relying on it operationally.
- Remember that conversational Telegram access exposes app context, so keep bot access restricted to your intended chat.
