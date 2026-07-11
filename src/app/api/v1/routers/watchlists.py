import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.v1.dependencies import get_watchlist_repository, require_current_user
from app.api.v1.schemas import (
    CurrentUser,
    WatchlistCreateRequest,
    WatchlistItemAddRequest,
    WatchlistItemResponse,
    WatchlistRenameRequest,
    WatchlistResponse,
)
from app.domain.watchlist.entities import Watchlist
from app.domain.watchlist.ports import WatchlistRepository

router = APIRouter(prefix="/watchlists", tags=["watchlists"])


async def _get_owned_watchlist(
    watchlist_id: str, user: CurrentUser, repository: WatchlistRepository
) -> Watchlist:
    """Return the watchlist if it exists and belongs to `user`, else raise 404.

    404 (not 403) even when the watchlist exists but belongs to someone else, so this
    endpoint never confirms another user's watchlist id exists.
    """
    watchlist = await repository.get(watchlist_id)
    if watchlist is None or watchlist.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Watchlist not found")
    return watchlist


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_watchlist(
    payload: WatchlistCreateRequest,
    user: Annotated[CurrentUser, Depends(require_current_user)],
    repository: Annotated[WatchlistRepository, Depends(get_watchlist_repository)],
) -> WatchlistResponse:
    """Create a new watchlist owned by the authenticated user."""
    watchlist = Watchlist(id=str(uuid.uuid4()), user_id=user.id, name=payload.name)
    created = await repository.create(watchlist)
    return WatchlistResponse.model_validate(created)


@router.get("")
async def list_watchlists(
    user: Annotated[CurrentUser, Depends(require_current_user)],
    repository: Annotated[WatchlistRepository, Depends(get_watchlist_repository)],
) -> list[WatchlistResponse]:
    """List every watchlist owned by the authenticated user."""
    watchlists = await repository.list_for_user(user.id)
    return [WatchlistResponse.model_validate(watchlist) for watchlist in watchlists]


@router.get("/{watchlist_id}")
async def get_watchlist(
    watchlist_id: str,
    user: Annotated[CurrentUser, Depends(require_current_user)],
    repository: Annotated[WatchlistRepository, Depends(get_watchlist_repository)],
) -> WatchlistResponse:
    """Return a single watchlist owned by the authenticated user."""
    watchlist = await _get_owned_watchlist(watchlist_id, user, repository)
    return WatchlistResponse.model_validate(watchlist)


@router.patch("/{watchlist_id}")
async def rename_watchlist(
    watchlist_id: str,
    payload: WatchlistRenameRequest,
    user: Annotated[CurrentUser, Depends(require_current_user)],
    repository: Annotated[WatchlistRepository, Depends(get_watchlist_repository)],
) -> WatchlistResponse:
    """Rename a watchlist owned by the authenticated user."""
    await _get_owned_watchlist(watchlist_id, user, repository)
    renamed = await repository.rename(watchlist_id, payload.name)
    return WatchlistResponse.model_validate(renamed)


@router.delete("/{watchlist_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_watchlist(
    watchlist_id: str,
    user: Annotated[CurrentUser, Depends(require_current_user)],
    repository: Annotated[WatchlistRepository, Depends(get_watchlist_repository)],
) -> None:
    """Delete a watchlist (and its items, via `ON DELETE CASCADE`) owned by the user."""
    await _get_owned_watchlist(watchlist_id, user, repository)
    await repository.delete(watchlist_id)


@router.get("/{watchlist_id}/items")
async def list_watchlist_items(
    watchlist_id: str,
    user: Annotated[CurrentUser, Depends(require_current_user)],
    repository: Annotated[WatchlistRepository, Depends(get_watchlist_repository)],
) -> list[WatchlistItemResponse]:
    """List every instrument tracked in a watchlist owned by the authenticated user."""
    await _get_owned_watchlist(watchlist_id, user, repository)
    items = await repository.list_items(watchlist_id)
    return [WatchlistItemResponse.model_validate(item) for item in items]


@router.post("/{watchlist_id}/items", status_code=status.HTTP_201_CREATED)
async def add_watchlist_item(
    watchlist_id: str,
    payload: WatchlistItemAddRequest,
    user: Annotated[CurrentUser, Depends(require_current_user)],
    repository: Annotated[WatchlistRepository, Depends(get_watchlist_repository)],
) -> WatchlistItemResponse:
    """Add an instrument (by symbol) to a watchlist owned by the authenticated user."""
    await _get_owned_watchlist(watchlist_id, user, repository)
    item = await repository.add_item(watchlist_id, payload.symbol.upper())
    return WatchlistItemResponse.model_validate(item)


@router.delete("/{watchlist_id}/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_watchlist_item(
    watchlist_id: str,
    item_id: str,
    user: Annotated[CurrentUser, Depends(require_current_user)],
    repository: Annotated[WatchlistRepository, Depends(get_watchlist_repository)],
) -> None:
    """Remove a single item from a watchlist owned by the authenticated user."""
    await _get_owned_watchlist(watchlist_id, user, repository)
    await repository.remove_item(watchlist_id, item_id)
