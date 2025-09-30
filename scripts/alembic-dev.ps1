#!/usr/bin/env pwsh

# Script de gestion Alembic pour le developpement
# Usage: ./scripts/alembic-dev.ps1 <command> [args...]

param(
    [Parameter(Mandatory=$true, Position=0)]
    [string]$Command,
    
    [Parameter(ValueFromRemainingArguments=$true)]
    [string[]]$Args
)

function Write-Info {
    param([string]$Message)
    Write-Host "[INFO] $Message" -ForegroundColor Blue
}

function Write-Success {
    param([string]$Message)
    Write-Host "[OK] $Message" -ForegroundColor Green
}

function Write-Warning {
    param([string]$Message)
    Write-Host "[WARN] $Message" -ForegroundColor Yellow
}

function Write-Error {
    param([string]$Message)
    Write-Host "[ERROR] $Message" -ForegroundColor Red
}

function Test-DockerCompose {
    try {
        $null = docker compose version
        return $true
    } catch {
        Write-Error "Docker Compose n'est pas installe ou accessible"
        return $false
    }
}

function Test-ApiContainer {
    $containerId = docker compose ps -q api
    if ([string]::IsNullOrEmpty($containerId)) {
        Write-Warning "Le conteneur API n'est pas en cours d'execution"
        Write-Info "Demarrage du conteneur API..."
        docker compose up -d api
        
        # Attendre que le container soit vraiment prêt
        $maxAttempts = 30
        $attempt = 0
        do {
            Start-Sleep -Seconds 1
            $containerId = docker compose ps -q api
            $status = docker compose ps api
            $attempt++
            
            if ($status -match "Up") {
                Write-Info "Conteneur API demarre avec succes"
                return $true
            }
        } while ($attempt -lt $maxAttempts)
    } else {
        # Vérifier que le container est bien en cours d'exécution
        $status = docker compose ps api
        if ($status -match "Up") {
            return $true
        }
    }
    
    Write-Error "Impossible de demarrer le conteneur API"
    return $false
}

function Invoke-Alembic {
    param([string[]]$AlembicArgs)
    
    if (-not (Test-DockerCompose)) { return }
    if (-not (Test-ApiContainer)) { return }
    
    # Construire la commande avec docker compose exec
    $dockerArgs = @("compose", "exec", "api", "alembic") + $AlembicArgs
    
    Write-Info "Execution: docker $($dockerArgs -join ' ')"
    
    try {
        & docker $dockerArgs
    } catch {
        Write-Error "Erreur lors de l'execution d'Alembic: $_"
        throw
    }
}

# Commandes disponibles
switch ($Command.ToLower()) {
    "revision" {
        if ($Args.Count -eq 0) {
            Write-Error "Usage: revision <message> [--autogenerate]"
            exit 1
        }
        
        # Joindre tous les arguments pour le message (sauf --autogenerate)
        $messageArgs = @()
        $autogenerate = $false
        
        foreach ($arg in $Args) {
            if ($arg -eq "--autogenerate" -or $arg -eq "-a") {
                $autogenerate = $true
            } else {
                $messageArgs += $arg
            }
        }
        
        if ($messageArgs.Count -eq 0) {
            Write-Error "Usage: revision <message> [--autogenerate]"
            exit 1
        }
        
        $message = $messageArgs -join " "
        $alembicArgs = @("revision", "-m", "`"$message`"")
        
        if ($autogenerate) {
            $alembicArgs += "--autogenerate"
        }
        
        Write-Info "Creation d'une nouvelle revision: $message"
        Invoke-Alembic $alembicArgs
        Write-Success "Revision creee avec succes!"
    }
    
    "upgrade" {
        $target = if ($Args.Count -gt 0) { $Args[0] } else { "head" }
        Write-Info "Mise a jour vers: $target"
        Invoke-Alembic @("upgrade", $target)
        Write-Success "Migration appliquee avec succes!"
    }
    
    "downgrade" {
        if ($Args.Count -eq 0) {
            Write-Error "Usage: downgrade <target>"
            exit 1
        }
        
        $target = $Args[0]
        Write-Warning "Retour en arriere vers: $target"
        Write-Host "Etes-vous sur? (y/N): " -NoNewline
        $confirmation = Read-Host
        
        if ($confirmation -eq "y" -or $confirmation -eq "Y") {
            Invoke-Alembic @("downgrade", $target)
            Write-Success "Retour en arriere effectue!"
        } else {
            Write-Info "Operation annulee"
        }
    }
    
    "current" {
        Write-Info "Version actuelle de la base de donnees:"
        Invoke-Alembic @("current")
    }
    
    "history" {
        Write-Info "Historique des migrations:"
        $historyArgs = @("history")
        if ($Args -contains "--verbose" -or $Args -contains "-v") {
            $historyArgs += "--verbose"
        }
        Invoke-Alembic $historyArgs
    }
    
    "heads" {
        Write-Info "Dernieres revisions disponibles:"
        Invoke-Alembic @("heads")
    }
    
    "show" {
        if ($Args.Count -eq 0) {
            Write-Error "Usage: show <revision>"
            exit 1
        }
        
        $revision = $Args[0]
        Write-Info "Details de la revision: $revision"
        Invoke-Alembic @("show", $revision)
    }
    
    "stamp" {
        if ($Args.Count -eq 0) {
            Write-Error "Usage: stamp <revision>"
            exit 1
        }
        
        $revision = $Args[0]
        Write-Info "Marquage de la base avec la revision: $revision"
        Invoke-Alembic @("stamp", $revision)
        Write-Success "Base marquee avec succes!"
    }
    
    "check" {
        Write-Info "Verification de l'etat des migrations..."
        try {
            Invoke-Alembic @("check")
            Write-Success "Base de donnees a jour!"
        } catch {
            Write-Warning "Des migrations sont en attente"
        }
    }
    
    "init" {
        Write-Info "Initialisation d'un nouveau projet Alembic..."
        if ($Args.Count -eq 0) {
            $directory = "alembic"
        } else {
            $directory = $Args[0]
        }
        Invoke-Alembic @("init", $directory)
        Write-Success "Projet Alembic initialise!"
    }
    
    "help" {
        Write-Host @"
Script de gestion Alembic pour le developpement

USAGE:
    ./scripts/alembic-dev.ps1 <command> [args...]

COMMANDES:
    revision <message> [--autogenerate]  Creer une nouvelle revision
    upgrade [target]                     Appliquer les migrations (defaut: head)
    downgrade <target>                   Revenir en arriere
    current                              Afficher la version actuelle
    history [--verbose]                  Afficher l'historique
    heads                                Afficher les dernieres revisions
    show <revision>                      Afficher les details d'une revision
    stamp <revision>                     Marquer la base avec une revision
    check                                Verifier l'etat des migrations
    init [directory]                     Initialiser un nouveau projet
    help                                 Afficher cette aide

EXEMPLES:
    ./scripts/alembic-dev.ps1 revision "Add user table" --autogenerate
    ./scripts/alembic-dev.ps1 upgrade
    ./scripts/alembic-dev.ps1 current
    ./scripts/alembic-dev.ps1 history --verbose
    ./scripts/alembic-dev.ps1 downgrade -1

PREREQUIS:
    - Docker et Docker Compose V2 installes (syntaxe 'docker compose')
    - Conteneur alembic-dev demarre automatiquement si necessaire
"@
    }
    
    default {
        Write-Error "Commande inconnue: $Command"
        Write-Info "Utilisez 'help' pour voir les commandes disponibles"
        exit 1
    }
}