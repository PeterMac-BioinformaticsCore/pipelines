import json
from pipeline_definition.types.step_type import Step

class StepContext:
    def __init__(self, step):
        self.__step = step
        self.__branchOutputsStack = list()
        self.__dependecnyContexts = list()

    def inheritContextOfBranch(self, prevCtx):
        outputsStackFromPrevContext = prevCtx.outputStackOfBranch()
        if not outputsStackFromPrevContext:
            return
        self.__branchOutputsStack.extend(outputsStackFromPrevContext)

    def outputStackOfBranch(self):
        outputStack = list()

        providesDict = {}
        providesDict[self.__step.id()] = self.__step.provides()
        outputDict = {}
        outputDict[self.__step.tag()] = providesDict
        outputStack.append(outputDict)

        outputStack.extend(self.__branchOutputsStack)

        return outputStack

    def addDependencyContextFrom(self, stepCtx ):
        dependencyContext = stepCtx.provides()
        self.__dependecnyContexts.append(dependencyContext)

    def provides(self):
        providesDict = {}
        providesDict[self.__step.id()] = self.__step.provides()
        outputDict = {}
        outputDict[self.__step.tag()] = providesDict
        return outputDict

    def providesFor(self, step):
        provides = self.provides()

        if not provides:
            return []

        tagSpecific = provides.get(step.tag())

        if not tagSpecific:
            return []

        stepSpecific = tagSpecific.get(step.id())
        if not stepSpecific:
            return []

        return stepSpecific

    def toJSON(self):
        return json.dumps(self, default=lambda o: o.__dict__,sort_keys=True, indent=4)

    def print(self):
        print(self.toJSON())


    def mapInput(self, input):

        doc = {}
        #Value provided?
        providedValue = self.__step.providedValueForRequirement( input[Step.STR_ID] )
        if providedValue:
            doc['provided'] = providedValue





        return doc


