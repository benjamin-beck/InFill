import adsk.core, adsk.fusion, traceback

ui = None
app = None
design = None
rootComp = None
handlers = []

def run(context):
    global ui
    global app
    global design
    global rootComp

    try:
        app = adsk.core.Application.get()
        ui = app.userInterface
        design = adsk.fusion.Design.cast(app.activeProduct)
        rootComp = design.rootComponent
        command = ui.commandDefinitions.itemById('InFoil')

        if not command:
            command = ui.commandDefinitions.addButtonDefinition("InFoil", "InFoilParameters", "")

        onCreateHandler = CommandCreatedHandler(ui, app, design, rootComp)
        handlers.append(onCreateHandler)
        command.commandCreated.add(onCreateHandler)
        command.execute()
        adsk.autoTerminate(False)

    except Exception as e:
        ui.messageBox(f"Error {str(e)}")
class CommandCreatedHandler(adsk.core.CommandCreatedEventHandler):
    def __init__(self, ui, app, design, rootComp):
        super().__init__()
        self.ui = ui
        self.app = app
        self.design = design
        self.rootComp = rootComp

    def notify(self, args):
        cmd = args.command
        inputs = cmd.commandInputs

        """-----GUI STUFF------"""
        inputs.addTextBoxCommandInput('label1', '', 'Select Infill Mode:', 1, True)
        #To-do add more infill modes
        dropdownInfill = inputs.addDropDownCommandInput(
            'dropdownInfill',
            'Choose Option',
            adsk.core.DropDownStyles.TextListDropDownStyle
        )
        dropdownInfill.listItems.add("90° Cross", True)
        dropdownInfill.listItems.add("Hexagonal", False)
        dropdownInfill.listItems.add("Triangular", False)
        # Create blank text element for spacing
        inputs.addTextBoxCommandInput('label2', '', '', 1, True)
        # Create text entry element for infill spacing (There is no way to set an infinite min/max so they its capped at |999999|cm)
        inputs.addIntegerSpinnerCommandInput("infillSpacing", "Infill Spacing", -999999, 999999, 1, 10)
        # Get sketch selection for the planform(Where it will apply the infill pattern
        sketchInput = inputs.addSelectionInput('sketchSel', 'Sketch Planform', 'Select a sketch')
        sketchInput.addSelectionFilter('Sketches')
        sketchInput.setSelectionLimits(1, 1)
        # Get body selection for the infill pattern to cut
        bodyInput = inputs.addSelectionInput('bodySel', 'Target Body', 'Select the solid body to modify')
        bodyInput.addSelectionFilter('Bodies')
        bodyInput.setSelectionLimits(1, 1)
        # Get the first chord profile line
        chordInput = inputs.addSelectionInput('chordSel', 'Chord Line', 'Select a chord line')
        chordInput.addSelectionFilter('SketchCurves')
        chordInput.setSelectionLimits(1, 3)
        # Get the second chord profile line
        chordInput2 = inputs.addSelectionInput('chordSel2', 'Chord Line2', 'Select a chord line')
        chordInput2.addSelectionFilter('SketchCurves')
        chordInput2.setSelectionLimits(1, 3)
        # Get guide rail 1
        railInput = inputs.addSelectionInput('railSel', 'Guide Rail Line 1', 'Select guide rail line')
        railInput.addSelectionFilter('SketchCurves')
        railInput.setSelectionLimits(1, 1)
        # Get guide rail 2
        railInput2 = inputs.addSelectionInput('railSel2', 'Guide Rail Line 2', 'Select guide rail line')
        railInput2.addSelectionFilter('SketchCurves')
        railInput2.setSelectionLimits(1, 1)

        onExecute = CommandExecuteHandler(ui, app, design, rootComp)
        cmd.execute.add(onExecute)
        handlers.append(onExecute)


class CommandExecuteHandler(adsk.core.CommandEventHandler):

    def __init__(self, ui, app, design, rootComp):
        super().__init__()
        self.ui = ui
        self.app = app
        self.design = design
        self.rootComp = rootComp
        self.generatedInfill = None
        self.booleanSubtractBody = None

    def notify(self, args):
        inputs = args.command.commandInputs

        infillTypeSelection = inputs.itemById('dropdownInfill')
        selectedInfillType = infillTypeSelection.selectedItem.name if infillTypeSelection else "None"
        infillSpacingSelectionInput = inputs.itemById('infillSpacing')
        infillSpacingSelection = infillSpacingSelectionInput.value if infillSpacingSelectionInput else None
        sketchPlanformSelectionInput = inputs.itemById('sketchSel')
        sketchPlanformSelection = sketchPlanformSelectionInput.selection(0).entity if sketchPlanformSelectionInput.selectionCount > 0 else None

        wingBodySelectionInput = inputs.itemById('bodySel')
        wingBodySelection = wingBodySelectionInput.selection(0).entity if wingBodySelectionInput.selectionCount > 0 else None
        targetBody = wingBodySelection

        chordCurveSelectionInput = inputs.itemById('chordSel')
        chordCurves = []
        if chordCurveSelectionInput.selectionCount > 0:
            for i in range(chordCurveSelectionInput.selectionCount):
                chordCurves.append(chordCurveSelectionInput.selection(i).entity)

        chordCurve2SelectionInput = inputs.itemById('chordSel2')
        chordCurves2 = []
        if chordCurve2SelectionInput.selectionCount > 0:
            for i in range(chordCurve2SelectionInput.selectionCount):
                chordCurves2.append(chordCurve2SelectionInput.selection(i).entity)

        guideRailCurveSelectionInput = inputs.itemById('railSel')
        guideRailCurveSelection = guideRailCurveSelectionInput.selection(0).entity if guideRailCurveSelectionInput.selectionCount > 0 else None
        guideRailCurve = guideRailCurveSelection

        guideRail2CurveSelectionInput = inputs.itemById('railSel2')
        guideRail2CurveSelection = guideRail2CurveSelectionInput.selection(0).entity if guideRail2CurveSelectionInput.selectionCount > 0 else None
        guideRail2Curve = guideRail2CurveSelection

        #Copy the target body to for creating infill
        self.CopyBody(wingBodySelection)
        #Generate the infill pattern and extrude voids
        self.GenerateInfill(sketchPlanformSelection, infillSpacingSelection)
        #
        self.ExtrudeCurve(chordCurves, chordCurves2, guideRailCurve, guideRail2Curve)
        self.ui.messageBox("Successfully Executed")

    """CopyBody:
    This just copies the target body to use for cutting the infill.
    """
    def CopyBody(self, body):
        self.booleanSubtractBody = body
        copyPasteFeatures = self.rootComp.features.copyPasteBodies
        copyFeature = copyPasteFeatures.add(body)
        copyFeature.bodies.item(0).name = "EngineeredInfill"

        for i in self.rootComp.bRepBodies:
            if i.name != "EngineeredInfill":
                i.isVisible = False

    """GenerateInfill:
    This function generates all of the lines/profiles for the infill. The way it does it is not optimal and takes quite a while to generate but works nonetheless.
    """
    def GenerateInfill(self, sketch, distance):
        self.ui.messageBox("Generating Infill")

        extrudeProfileCentroids = []

        infillConstraints = sketch.profiles.item(0).boundingBox
        profile = sketch.profiles.item(0)

        # This should be the bottom corner
        corner1 = infillConstraints.minPoint.asArray()
        # This should be top corner
        corner2 = infillConstraints.maxPoint.asArray()

        sketchLines = sketch.sketchCurves.sketchLines

        # Bounds
        lengthX = corner2[0] - corner1[0]
        lengthY = corner2[1] - corner1[1]

        # Params
        offset = 0.01

        if lengthX < lengthY:
            numCrossesX = lengthX / distance
            numCrossesY = lengthY / distance
            longYcase = True
        else:
            numCrossesY = lengthX / distance
            numCrossesX = lengthY / distance
            longYcase = False

        # Crosshatch lines generation
        q = 0
        for i in range(int(numCrossesY) + 1):
            if longYcase:
                sketchLines.addByTwoPoints(adsk.core.Point3D.create(corner1[0], corner1[1] + q, corner1[2]),
                                           adsk.core.Point3D.create(corner1[0] + lengthX, corner1[1] + lengthX + q, corner2[2]))
                if (i < numCrossesX):
                    sketchLines.addByTwoPoints(adsk.core.Point3D.create(corner1[0], corner1[1] - q, corner1[2]),
                                               adsk.core.Point3D.create(corner1[0] + lengthX, corner1[1] + lengthX - q, corner2[2]))
            else:
                pass
                sketchLines.addByTwoPoints(adsk.core.Point3D.create(corner1[0] + q, corner1[1], corner1[2]),
                                           adsk.core.Point3D.create(corner1[0] + lengthY + q, corner1[1] + lengthY, corner2[2]))
                if (i < numCrossesX):
                    sketchLines.addByTwoPoints(adsk.core.Point3D.create(corner1[0] - q, corner1[1], corner1[2]),
                                               adsk.core.Point3D.create(corner1[0] + lengthY - q, corner1[1] + lengthY, corner2[2]))

            q = q + distance

        q = 0
        for i in range(int(numCrossesY) + 1):
            # Dir 1
            if longYcase:
                pass
                sketchLines.addByTwoPoints(adsk.core.Point3D.create(corner1[0], corner1[1] + lengthX + q, corner1[2]),
                                           adsk.core.Point3D.create(corner1[0] + lengthX, corner1[1] + q, corner2[2]))
                # Filling the backwards corner
                if (i < numCrossesX):
                    sketchLines.addByTwoPoints(adsk.core.Point3D.create(corner1[0], corner1[1] + lengthX - q, corner1[2]),
                                               adsk.core.Point3D.create(corner1[0] + lengthX, corner1[1] - q, corner2[2]))
            else:
                sketchLines.addByTwoPoints(adsk.core.Point3D.create(corner1[0] + q, corner1[1] + lengthY, corner1[2]),
                                           adsk.core.Point3D.create(corner1[0] + lengthY + q, corner1[1], corner2[2]))
                # Filling the backwards corner
                if (i < numCrossesX):
                    sketchLines.addByTwoPoints(adsk.core.Point3D.create(corner1[0] - q, corner1[1] + lengthY, corner1[2]),
                                               adsk.core.Point3D.create(corner1[0] + lengthY - q, corner1[1], corner2[2]))

            q = q + distance

        for profiles in sketch.profiles:
            #The 2 denotes high accuracy for the calculations set to 0 for much faster calculations
            profileCentroid = profiles.areaProperties(2).centroid
            extrudeProfileCentroids.append(profileCentroid)


        #Offset line generation
        q = 0
        for i in range(int(numCrossesY) + 1):
            # Dir 1
            if longYcase:
                sketchLines.addByTwoPoints(adsk.core.Point3D.create(corner1[0], corner1[1] + q + offset, corner1[2]),
                                           adsk.core.Point3D.create(corner1[0] + lengthX, corner1[1] + lengthX + q + offset, corner2[2]))
                if (i < numCrossesX):
                    if (q != 0):
                        sketchLines.addByTwoPoints(adsk.core.Point3D.create(corner1[0], corner1[1] - q + offset, corner1[2]),
                                                   adsk.core.Point3D.create(corner1[0] + lengthX, corner1[1] + lengthX - q + offset, corner2[2]))
            else:
                pass
                sketchLines.addByTwoPoints(adsk.core.Point3D.create(corner1[0] + q + offset, corner1[1], corner1[2]),
                                           adsk.core.Point3D.create(corner1[0] + lengthY + q + offset, corner1[1] + lengthY, corner2[2]))
                if (i < numCrossesX):
                    if (q != 0):
                        sketchLines.addByTwoPoints(adsk.core.Point3D.create(corner1[0] - q + offset, corner1[1], corner1[2]),
                                                   adsk.core.Point3D.create(corner1[0] + lengthY - q + offset, corner1[1] + lengthY, corner2[2]))

            q = q + distance

        q = 0
        for i in range(int(numCrossesY) + 1):
            if longYcase:
                pass
                sketchLines.addByTwoPoints(adsk.core.Point3D.create(corner1[0], corner1[1] + lengthX + q + offset, corner1[2]),
                                           adsk.core.Point3D.create(corner1[0] + lengthX, corner1[1] + q + offset, corner2[2]))
                if (i < numCrossesX):
                    if (q != 0):
                        sketchLines.addByTwoPoints(adsk.core.Point3D.create(corner1[0], corner1[1] + lengthX - q + offset, corner1[2]),
                                                   adsk.core.Point3D.create(corner1[0] + lengthX, corner1[1] - q + offset, corner2[2]))
            else:
                sketchLines.addByTwoPoints(adsk.core.Point3D.create(corner1[0] + q + offset, corner1[1] + lengthY, corner1[2]),
                                           adsk.core.Point3D.create(corner1[0] + lengthY + q + offset, corner1[1], corner2[2]))
                if (i < numCrossesX):
                    if (q != 0):
                        sketchLines.addByTwoPoints(adsk.core.Point3D.create(corner1[0] - q + offset, corner1[1] + lengthY, corner1[2]),
                                                   adsk.core.Point3D.create(corner1[0] + lengthY - q + offset, corner1[1], corner2[2]))

            q = q + distance

        while self.TrimLinesOutsideBoundary(sketch, corner1, corner2):
            pass

        self.ExtrudeVoids(sketch, extrudeProfileCentroids, infillConstraints.minPoint, infillConstraints.maxPoint)

    """TO-DO: This only half works(closed profiles outisde of the planform dont get deleted). Its not acutally that important so I kinda gave up for now. Didn't even bother
    trying to add comment's LOL."""

    """TrimLinesOutsideBoundary:
    This is a helper function for the generateInfill function, it looks for lines that have a start and end point outside the planform sketch.
    """
    def TrimLinesOutsideBoundary(self, sketch, corner1, corner2):
        trimmedAny = False
        validLines = 0
        attemptedTrims = 0
        successfulTrims = 0
        skippedLines = 0
        lines = [line for line in sketch.sketchCurves.sketchLines]
        for line in lines:
            if not line.isValid:
                skippedLines += 1
                continue
            validLines += 1
            startPt = line.startSketchPoint.geometry
            endPt = line.endSketchPoint.geometry
            startArr = startPt.asArray()
            endArr = endPt.asArray()
            startOutside = not (corner1[0] <= startArr[0] <= corner2[0] and corner1[1] <= startArr[1] <= corner2[1])
            endOutside = not (corner1[0] <= endArr[0] <= corner2[0] and corner1[1] <= endArr[1] <= corner2[1])
            if startOutside or endOutside:
                attemptedTrims += 1
                trimPt = endPt if endOutside else startPt
                try:
                    result = line.trim(trimPt)
                    if result and result.count > 0:
                        trimmedAny = True
                        successfulTrims += 1
                    else:
                        pass
                except Exception as e:
                    pass
        return trimmedAny

    """ExtrudeVoids:
    This is just a helper function for the generateInfill, why I made it separate I dont remember but I did so wtevr. It basically uses the centroid of all the profiles
    generated in the generateInfill function and makes sure that it's within tolerance(only selects the profiles big squares not the small rectangles). There are some 
    edge cases that it will not work. Once it has the profiles selected it will cut them from the body copied in copyBody function."""
    def ExtrudeVoids(self, sketch, referenceCentroids, min, max):
        extrudes = self.rootComp.features.extrudeFeatures
        extrudeProfiles = adsk.core.ObjectCollection.create()
        tolerance = 0.05
        for profiles in sketch.profiles:
            centroid = profiles.areaProperties().centroid
            for referenceCentroid in referenceCentroids:
                if abs(referenceCentroid.x - centroid.x) < tolerance and abs(referenceCentroid.y - centroid.y) < tolerance:
                    if min.x < centroid.x < max.x and min.y < centroid.y < max.y:
                        extrudeProfiles.add(profiles)

        extInput = extrudes.createInput(extrudeProfiles, adsk.fusion.FeatureOperations.CutFeatureOperation)
        distance = adsk.core.ValueInput.createByReal(100)
        extInput.setTwoSidesDistanceExtent(distance, distance)

        infill = extrudes.add(extInput)
        self.generatedInfill = infill.bodies.item(0)

    """ExtrudeCurve:
    This function lofts a surface between the two chord curves bounded by the rail curves then extrudes that surface to thickness of 0.04 to cut the engineered infill 
    down the middle. After the infill is spit it will try to combine all the new bodies(there will be many) sometimes it works sometimes not but it's ok... because 
    the boolean subtract will still loop over all created bodies when subtracting from the target body. 
    """
    def ExtrudeCurve(self, curve, curve2, path1, path2):
        try:
            curves = adsk.core.ObjectCollection.create()
            for c in curve:
                curves.add(c)

            curves2 = adsk.core.ObjectCollection.create()
            for c in curve2:
                curves2.add(c)

            profile1 = self.rootComp.features.createPath(curves, True)
            profile2 = self.rootComp.features.createPath(curves2, True)


            rail1 = self.rootComp.features.createPath(path1, False)
            rail2 = self.rootComp.features.createPath(path2, False)

            loftFeats = self.rootComp.features.loftFeatures
            loftInput = loftFeats.createInput(adsk.fusion.FeatureOperations.NewBodyFeatureOperation)
            loftInput.loftSections.add(profile1)
            loftInput.loftSections.add(profile2)

            loftInput.centerLineOrRails.addRail(rail1)
            loftInput.centerLineOrRails.addRail(rail2)

            loftInput.isSolid = False
            loft = loftFeats.add(loftInput)

            thickenFeature = self.rootComp.features.thickenFeatures

            faces = adsk.core.ObjectCollection.create()
            body = loft.bodies.item(0)
            for face in body.faces:
                faces.add(face)

            thickenInput = thickenFeature.createInput(faces, adsk.core.ValueInput.createByReal(0.02), True, 3)
            splittingBody = thickenFeature.add(thickenInput)
            splittingBody = splittingBody.bodies.item(0)

            combineFeats = self.rootComp.features.combineFeatures

            tools = adsk.core.ObjectCollection.create()
            tools.add(splittingBody)

            cutIn = combineFeats.createInput(self.generatedInfill, tools)
            cutIn.operation = adsk.fusion.FeatureOperations.CutFeatureOperation
            cutIn.isKeepToolBodies = False
            cutIn.isNewComponent = False

            cutFeat = combineFeats.add(cutIn)

            resBodies = cutFeat.bodies

            #For whatever reason this doesnt work, something to do with fusion; doesnt work with the gui feature either.
            tools2 = None
            if resBodies and resBodies.count > 1:
                target = resBodies.item(0)
                tools2 = adsk.core.ObjectCollection.create()
                for i in range(1, resBodies.count):
                    tools2.add(resBodies.item(i))

                joinIn = combineFeats.createInput(target, tools2)
                joinIn.operation = adsk.fusion.FeatureOperations.JoinFeatureOperation
                joinIn.isKeepToolBodies = False
                joinIn.isNewComponent = False

                joinFeat = combineFeats.add(joinIn)

            if tools2 is not None:
                tools2.add(self.generatedInfill)
                subtractInfillFromBody = combineFeats.createInput(self.booleanSubtractBody, tools2)
                subtractInfillFromBody.operation = adsk.fusion.FeatureOperations.CutFeatureOperation
                combineFeats.add(subtractInfillFromBody)
                self.booleanSubtractBody.isVisible = True

        except Exception as e:
            self.ui.messageBox(f"Error {str(e)}")
