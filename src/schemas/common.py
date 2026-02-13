from enum import Enum

class Equipment(str, Enum):
    bodyweight="bodyweight"
    dumbbell="dumbbell"
    barbell="barbell"
    resistance_band="resistance_band"
    machine="machine"
    
class Injury(str, Enum):
    shoulder="shoulder"
    knee="knee"
    back="back"
    wrist="wrist"
    ankle="ankle"
    none="none"

class Gender(str, Enum):
    male="male"
    female="female"
    
class ExperienceLevel(str, Enum):
    beginner="beginner"
    intermediate="intermediate"
    advanced="advanced"

class FitnessGoal(str, Enum):
    weight_loss="weight_loss"
    muscle_gain="muscle_gain"
    strength_gain="strength_gain"
    endurance_gain="endurance_gain"
    flexibility_gain="flexibility_gain"
    general_fitness="general_fitness"

