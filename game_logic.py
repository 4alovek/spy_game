import random
from typing import List, Optional, Dict
from enum import Enum


class GameResult(Enum):
    WORKERS_WIN = "workers"
    SPY_WIN = "spy"


class Player:
    def __init__(self, user_id: int, username: str, display_name: Optional[str] = None):
        self.user_id = user_id
        self.username = username
        self.display_name = display_name or username  # Игровое имя
        self.is_spy = False
        self.workplace: Optional[str] = None
    
    def set_display_name(self, name: str):
        """Установить игровое имя"""
        self.display_name = name
    
    def __repr__(self):
        return f"Player({self.display_name}, spy={self.is_spy})"


class Lobby:
    WORKPLACES = [
        "Банк",
        "Больница",
        "Школа",
        "Ресторан",
        "Полицейский участок",
        "Пожарная станция",
        "Аэропорт",
        "Театр",
        "Кинотеатр",
        "Отель",
        "Супермаркет",
        "Завод",
        "Офис IT-компании",
        "Университет",
        "Библиотека",
        "Спортзал",
        "Парикмахерская",
        "Автосервис",
        "Почта",
        "Музей",
        "Кафе",
        "Пиццерия",
        "Бар",
        "Ночной клуб",
        "Казино",
        "Цирк",
        "Зоопарк",
        "Аквапарк",
        "Боулинг",
        "Караоке-бар",
        "Фитнес-клуб",
        "Салон красоты",
        "Массажный салон",
        "Ветеринарная клиника",
        "Аптека",
        "Торговый центр",
        "Книжный магазин",
        "Цветочный магазин",
        "Ювелирный магазин",
        "Автомойка",
        "Стоматология",
        "Лаборатория",
        "Радиостанция",
        "Телестудия",
        "Издательство",
        "Типография",
        "Фотостудия",
        "Военная база",
        "Посольство",
        "Круизный лайнер"
    ]
    
    def __init__(self, lobby_id: str, organizer_id: int, organizer_username: str):
        self.lobby_id = lobby_id
        self.organizer_id = organizer_id
        self.organizer_username = organizer_username
        self.players: List[Player] = []
        self.game_started = False
        self.current_workplace: Optional[str] = None
        self.spy: Optional[Player] = None
        self.custom_workplaces: List[str] = []  # Кастомные места работы
        
        # Состояние остановки игры
        self.game_stopped = False
        self.stopped_by: Optional[Player] = None
        self.accused_player: Optional[Player] = None  # Кого обвинил работник
        self.guessed_workplace: Optional[str] = None  # Что угадал шпион
        self.votes: Dict[int, bool] = {}  # user_id -> голос (True = Да, False = Нет)
    
    def add_player(self, user_id: int, username: str, display_name: Optional[str] = None) -> bool:
        """Добавить игрока в лобби. Возвращает True если успешно."""
        if self.game_started:
            return False
        
        # Проверяем, не добавлен ли уже игрок
        if any(p.user_id == user_id for p in self.players):
            return False
        
        player = Player(user_id, username, display_name)
        self.players.append(player)
        return True
    
    def remove_player(self, user_id: int) -> bool:
        """Удалить игрока из лобби. Возвращает True если успешно."""
        if self.game_started:
            return False
        
        initial_count = len(self.players)
        self.players = [p for p in self.players if p.user_id != user_id]
        return len(self.players) < initial_count
    
    def start_game(self) -> bool:
        """Начать игру. Возвращает True если успешно."""
        if self.game_started:
            return False
        
        if len(self.players) < 3:
            return False
        
        # Объединяем стандартные и кастомные места работы
        all_workplaces = self.WORKPLACES + self.custom_workplaces
        
        # Выбираем случайное место работы
        self.current_workplace = random.choice(all_workplaces)
        
        # Выбираем случайного шпиона
        self.spy = random.choice(self.players)
        self.spy.is_spy = True
        
        # Назначаем место работы всем работникам
        for player in self.players:
            if not player.is_spy:
                player.workplace = self.current_workplace
        
        self.game_started = True
        self.game_stopped = False
        self.stopped_by = None
        self.accused_player = None
        self.guessed_workplace = None
        self.votes = {}
        return True
    
    def end_game(self, result: GameResult) -> None:
        """Завершить игру и сбросить состояние."""
        self.game_started = False
        self.current_workplace = None
        self.spy = None
        self.game_stopped = False
        self.stopped_by = None
        self.accused_player = None
        self.guessed_workplace = None
        self.votes = {}
        
        # Сбрасываем роли игроков
        for player in self.players:
            player.is_spy = False
            player.workplace = None
    
    def get_player_role_info(self, user_id: int) -> Optional[Dict]:
        """Получить информацию о роли игрока."""
        if not self.game_started:
            return None
        
        player = next((p for p in self.players if p.user_id == user_id), None)
        if not player:
            return None
        
        return {
            "is_spy": player.is_spy,
            "workplace": player.workplace,
            "player_count": len(self.players)
        }
    
    def get_players_list(self) -> List[str]:
        """Получить список имён игроков."""
        return [p.display_name for p in self.players]
    
    def get_player(self, user_id: int) -> Optional[Player]:
        """Получить игрока по user_id."""
        return next((p for p in self.players if p.user_id == user_id), None)
    
    def set_player_name(self, user_id: int, name: str) -> bool:
        """Установить игровое имя игроку. Возвращает True если успешно."""
        player = self.get_player(user_id)
        if player and not self.game_started:
            player.set_display_name(name)
            return True
        return False
    
    def add_custom_workplace(self, workplace: str) -> bool:
        """Добавить кастомное место работы. Возвращает True если успешно."""
        if self.game_started:
            return False
        
        if workplace in self.custom_workplaces or workplace in self.WORKPLACES:
            return False
        
        self.custom_workplaces.append(workplace)
        return True
    
    def get_all_workplaces(self) -> List[str]:
        """Получить список всех мест работы (стандартные + кастомные)."""
        return self.WORKPLACES + self.custom_workplaces
    
    def stop_game_by_worker(self, user_id: int, accused_id: int) -> Optional[str]:
        """Остановка игры работником с обвинением. Возвращает результат или None."""
        if not self.game_started or self.game_stopped:
            return None
        
        player = self.get_player(user_id)
        accused = self.get_player(accused_id)
        
        if not player or not accused or player.is_spy:
            return None
        
        self.game_stopped = True
        self.stopped_by = player
        self.accused_player = accused
        
        # Проверяем правильность обвинения
        if accused.is_spy:
            return "workers_win"
        else:
            return "spy_win"
    
    def stop_game_by_spy(self, user_id: int) -> bool:
        """Остановка игры шпионом. Возвращает True если успешно."""
        if not self.game_started or self.game_stopped:
            return False
        
        player = self.get_player(user_id)
        
        if not player or not player.is_spy:
            return False
        
        self.game_stopped = True
        self.stopped_by = player
        return True
    
    def set_spy_guess(self, workplace: str) -> bool:
        """Установить догадку шпиона о месте работы. Возвращает True если успешно."""
        if not self.game_stopped or not self.stopped_by or not self.stopped_by.is_spy:
            return False
        
        self.guessed_workplace = workplace
        return True
    
    def vote(self, user_id: int, vote: bool) -> bool:
        """Проголосовать (только для работников). Возвращает True если успешно."""
        player = self.get_player(user_id)
        
        if not player or player.is_spy or not self.guessed_workplace:
            return False
        
        self.votes[user_id] = vote
        return True
    
    def get_vote_result(self) -> Optional[str]:
        """Подсчитать голоса и определить победителя. Возвращает результат или None."""
        if not self.guessed_workplace:
            return None
        
        workers_count = len([p for p in self.players if not p.is_spy])
        
        # Проверяем, все ли работники проголосовали
        if len(self.votes) < workers_count:
            return None
        
        yes_votes = sum(1 for vote in self.votes.values() if vote)
        
        # Для победы шпиона нужно больше половины голосов "Да"
        if yes_votes > workers_count / 2:
            return "spy_win"
        else:
            return "workers_win"
    
    def get_workers(self) -> List[Player]:
        """Получить список работников."""
        return [p for p in self.players if not p.is_spy]
    
    def is_organizer(self, user_id: int) -> bool:
        """Проверить, является ли пользователь организатором."""
        return user_id == self.organizer_id


class GameManager:
    def __init__(self):
        self.lobbies: Dict[str, Lobby] = {}
    
    def create_lobby(self, organizer_id: int, organizer_username: str) -> str:
        """Создать новое лобби. Возвращает ID лобби."""
        lobby_id = self._generate_lobby_id()
        lobby = Lobby(lobby_id, organizer_id, organizer_username)
        self.lobbies[lobby_id] = lobby
        return lobby_id
    
    def get_lobby(self, lobby_id: str) -> Optional[Lobby]:
        """Получить лобби по ID."""
        return self.lobbies.get(lobby_id)
    
    def delete_lobby(self, lobby_id: str) -> bool:
        """Удалить лобби. Возвращает True если успешно."""
        if lobby_id in self.lobbies:
            del self.lobbies[lobby_id]
            return True
        return False
    
    def _generate_lobby_id(self) -> str:
        """Генерировать уникальный ID лобби."""
        while True:
            lobby_id = str(random.randint(1000, 9999))
            if lobby_id not in self.lobbies:
                return lobby_id
