#!/bin/bash

# Scripts utilitaires pour Alembic en développement

set -e

COMPOSE_PROJECT="fastapi-ecommerce"

# Couleurs pour les logs
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

echo_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

echo_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

echo_error() {
    echo -e "${RED}❌ $1${NC}"
}

# Fonction pour exécuter Alembic
run_alembic() {
    echo_info "Exécution de: alembic $*"
    docker-compose --profile alembic run --rm alembic alembic "$@"
}

# Menu d'aide
show_help() {
    echo "🚀 Script utilitaire Alembic pour le développement"
    echo ""
    echo "Usage: $0 [COMMAND] [OPTIONS]"
    echo ""
    echo "Commands:"
    echo "  init                     Initialise Alembic (première fois)"
    echo "  revision [message]       Génère une nouvelle migration"
    echo "  upgrade [revision]       Applique les migrations (défaut: head)"
    echo "  downgrade [revision]     Revient à une révision précédente"
    echo "  history                  Affiche l'historique des migrations"
    echo "  current                  Affiche la révision actuelle"
    echo "  show [revision]          Affiche le contenu d'une révision"
    echo "  heads                    Affiche les révisions head"
    echo "  merge [revisions]        Merge plusieurs heads"
    echo "  stamp [revision]         Marque la base comme étant à cette révision"
    echo "  check                    Vérifie si la base est à jour"
    echo ""
    echo "Examples:"
    echo "  $0 revision \"Add user table\""
    echo "  $0 upgrade"
    echo "  $0 history"
    echo "  $0 current"
}

# Vérifications préalables
check_docker() {
    if ! command -v docker-compose &> /dev/null; then
        echo_error "docker-compose n'est pas installé ou accessible"
        exit 1
    fi
}

# Commandes principales
case "${1:-help}" in
    "init")
        echo_info "Initialisation d'Alembic..."
        run_alembic init alembic
        echo_success "Alembic initialisé avec succès!"
        ;;
    
    "revision")
        MESSAGE="${2:-Auto-generated revision}"
        echo_info "Génération d'une nouvelle migration: $MESSAGE"
        run_alembic revision --autogenerate -m "$MESSAGE"
        echo_success "Migration générée avec succès!"
        ;;
    
    "upgrade")
        REVISION="${2:-head}"
        echo_info "Application des migrations jusqu'à: $REVISION"
        run_alembic upgrade "$REVISION"
        echo_success "Migrations appliquées avec succès!"
        ;;
    
    "downgrade")
        REVISION="${2:-}"
        if [ -z "$REVISION" ]; then
            echo_error "Veuillez spécifier une révision pour le downgrade"
            echo "Usage: $0 downgrade [revision]"
            exit 1
        fi
        echo_warning "Downgrade vers: $REVISION"
        echo_warning "Cette opération peut supprimer des données!"
        read -p "Êtes-vous sûr? (y/N): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            run_alembic downgrade "$REVISION"
            echo_success "Downgrade effectué avec succès!"
        else
            echo_info "Opération annulée"
        fi
        ;;
    
    "history")
        echo_info "Historique des migrations:"
        run_alembic history --verbose
        ;;
    
    "current")
        echo_info "Révision actuelle:"
        run_alembic current --verbose
        ;;
    
    "show")
        REVISION="${2:-head}"
        echo_info "Contenu de la révision: $REVISION"
        run_alembic show "$REVISION"
        ;;
    
    "heads")
        echo_info "Révisions head:"
        run_alembic heads --verbose
        ;;
    
    "merge")
        if [ -z "$2" ]; then
            echo_error "Veuillez spécifier les révisions à merger"
            echo "Usage: $0 merge \"rev1 rev2\""
            exit 1
        fi
        echo_info "Merge des révisions: $2"
        run_alembic merge $2
        echo_success "Merge effectué avec succès!"
        ;;
    
    "stamp")
        REVISION="${2:-head}"
        echo_info "Marquage de la base à la révision: $REVISION"
        run_alembic stamp "$REVISION"
        echo_success "Base marquée avec succès!"
        ;;
    
    "check")
        echo_info "Vérification de l'état des migrations..."
        if run_alembic check; then
            echo_success "Base de données à jour!"
        else
            echo_warning "Des migrations sont en attente"
        fi
        ;;
    
    "help"|"--help"|"-h")
        show_help
        ;;
    
    *)
        echo_error "Commande inconnue: $1"
        echo ""
        show_help
        exit 1
        ;;
esac