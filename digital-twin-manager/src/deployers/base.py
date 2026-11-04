from abc import ABC, abstractmethod

class Deployer(ABC):
  @abstractmethod
  def log(self, **kwargs):
    pass

  @abstractmethod
  def deploy(self, **kwargs):
    pass

  @abstractmethod
  def destroy(self, **kwargs):
    pass

  @abstractmethod
  def info(self, **kwargs):
    pass
